from __future__ import absolute_import, division, print_function, unicode_literals

from gratipay.testing import Harness
from gratipay.models.participant.mixins import identity, Identity
from gratipay.models.participant.mixins.identity import _validate_info
from gratipay.models.participant.mixins.identity import ParticipantIdentityInfoInvalid
from gratipay.models.participant.mixins.identity import ParticipantIdentitySchemaUnknown
from pytest import raises


class Tests(Harness):

    @classmethod
    def setUpClass(cls):
        Harness.setUpClass()
        cls.TTO = cls.db.one("SELECT id FROM countries WHERE code3='TTO'")
        cls.USA = cls.db.one("SELECT id FROM countries WHERE code3='USA'")

        def _failer(info):
            raise ParticipantIdentityInfoInvalid('You failed.')
        identity.schema_validators['impossible'] = _failer

    @classmethod
    def tearDownClass(cls):
        del identity.schema_validators['impossible']

    def setUp(self):
        self.crusher = self.make_participant('crusher', email_address='foo@example.com')

    def assert_events(self, crusher_id, identity_ids, country_ids, actions):
        events = self.db.all("SELECT * FROM events ORDER BY ts ASC")
        nevents = len(events)

        assert [e.type for e in events] == ['participant'] * nevents
        assert [e.payload['id'] for e in events] == [crusher_id] * nevents
        assert [e.payload['identity_id'] for e in events] == identity_ids
        assert [e.payload['country_id'] for e in events] == country_ids
        assert [e.payload['action'] for e in events] == actions


    # rii - retrieve_identity_info

    def test_rii_retrieves_identity_info(self):
        self.crusher.store_identity_info(self.USA, 'nothing-enforced', {'name': 'Crusher'})
        assert self.crusher.retrieve_identity_info(self.USA)['name'] == 'Crusher'

    def test_rii_retrieves_identity_when_there_are_multiple_identities(self):
        self.crusher.store_identity_info(self.USA, 'nothing-enforced', {'name': 'Crusher'})
        self.crusher.store_identity_info(self.TTO, 'nothing-enforced', {'name': 'Bruiser'})
        assert self.crusher.retrieve_identity_info(self.USA)['name'] == 'Crusher'
        assert self.crusher.retrieve_identity_info(self.TTO)['name'] == 'Bruiser'

    def test_rii_returns_None_if_there_is_no_identity_info(self):
        assert self.crusher.retrieve_identity_info(self.USA) is None

    def test_rii_logs_event(self):
        iid = self.crusher.store_identity_info(self.TTO, 'nothing-enforced', {'name': 'Crusher'})
        self.crusher.retrieve_identity_info(self.TTO)
        self.assert_events( self.crusher.id
                          , [iid, iid]
                          , [self.TTO, self.TTO]
                          , ['insert identity', 'retrieve identity']
                           )

    def test_rii_still_logs_an_event_when_noop(self):
        self.crusher.retrieve_identity_info(self.TTO)
        self.assert_events( self.crusher.id
                          , [None]
                          , [self.TTO]
                          , ['retrieve identity']
                           )


    # lim - list_identity_metadata

    def test_lim_lists_identity_metadata(self):
        self.crusher.store_identity_info(self.USA, 'nothing-enforced', {'name': 'Crusher'})
        assert [x.country.code3 for x in self.crusher.list_identity_metadata()] == ['USA']

    def test_lim_lists_metadata_for_multiple_identities(self):
        for country in (self.USA, self.TTO):
            self.crusher.store_identity_info(country, 'nothing-enforced', {'name': 'Crusher'})
        assert [x.country.code3 for x in self.crusher.list_identity_metadata()] == ['TTO', 'USA']


    # sii - store_identity_info

    def test_sii_sets_identity_info(self):
        self.crusher.store_identity_info(self.TTO, 'nothing-enforced', {'name': 'Crusher'})
        assert [x.country.code3 for x in self.crusher.list_identity_metadata()] == ['TTO']

    def test_sii_sets_a_second_identity(self):
        self.crusher.store_identity_info(self.TTO, 'nothing-enforced', {'name': 'Crusher'})
        self.crusher.store_identity_info(self.USA, 'nothing-enforced', {'name': 'Crusher'})
        assert [x.country.code3 for x in self.crusher.list_identity_metadata()] == ['TTO', 'USA']

    def test_sii_overwrites_first_identity(self):
        self.crusher.store_identity_info(self.TTO, 'nothing-enforced', {'name': 'Crusher'})
        self.crusher.store_identity_info(self.TTO, 'nothing-enforced', {'name': 'Bruiser'})
        assert [x.country.code3 for x in self.crusher.list_identity_metadata()] == ['TTO']
        assert self.crusher.retrieve_identity_info(self.TTO)['name'] == 'Bruiser'

    def test_sii_validates_identity(self):
        raises( ParticipantIdentityInfoInvalid
              , self.crusher.store_identity_info
              , self.TTO
              , 'impossible'
              , {'foo': 'bar'}
               )

    def test_sii_happily_overwrites_schema_name(self):
        packed = Identity.encrypting_packer.pack({'name': 'Crusher'})
        self.db.run( "INSERT INTO participant_identities "
                     "(participant_id, country_id, schema_name, info) "
                     "VALUES (%s, %s, %s, %s)"
                   , (self.crusher.id, self.TTO, 'flah', packed)
                    )
        assert [x.schema_name for x in self.crusher.list_identity_metadata()] == ['flah']
        self.crusher.store_identity_info(self.TTO, 'nothing-enforced', {'name': 'Crusher'})
        assert [x.schema_name for x in self.crusher.list_identity_metadata()] == \
                                                                               ['nothing-enforced']

    def test_sii_logs_event(self):
        iid = self.crusher.store_identity_info(self.TTO, 'nothing-enforced', {'name': 'Crusher'})
        self.assert_events(self.crusher.id, [iid], [self.TTO], ['insert identity'])


    # _vi - _validate_info

    def test__vi_validates_info(self):
        err = raises(ParticipantIdentityInfoInvalid, _validate_info, 'impossible', {'foo': 'bar'})
        assert err.value.message == 'You failed.'

    def test__vi_chokes_on_unknown_schema(self):
        err = raises(ParticipantIdentitySchemaUnknown, _validate_info, 'floo-floo', {'foo': 'bar'})
        assert err.value.message == "unknown schema 'floo-floo'"
