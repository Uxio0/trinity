import os
import yaml
import pytest

from py_ecc import bls
from ssz.tools import (
    from_formatted_dict,
    to_formatted_dict,
)

from eth2.configs import (
    Eth2Config,
)
from eth2.beacon.db.chain import BeaconChainDB
from eth2.beacon.tools.misc.ssz_vector import (
    override_vector_lengths,
)
from eth2.beacon.types.states import BeaconState
from eth2.beacon.state_machines.forks.serenity.blocks import SerenityBeaconBlock
from eth2.beacon.state_machines.forks.serenity import (
    SerenityStateMachine,
)

# Test files
ROOT_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

BASE_FIXTURE_PATH = os.path.join(ROOT_PROJECT_DIR, '../../', 'eth2-fixtures', 'state')

FILE_NAMES = [
    "sanity-check_small-config_32-vals.yaml",
    "sanity-check_default-config_100-vals.yaml",
]

#
# Mock bls verification for these tests
#
bls = bls


def mock_bls_verify(message_hash, pubkey, signature, domain):
    return True


def mock_bls_verify_multiple(pubkeys,
                             message_hashes,
                             signature,
                             domain):
    return True


@pytest.fixture(autouse=True)
def mock_bls(mocker, request):
    if 'noautofixt' in request.keywords:
        return

    mocker.patch('py_ecc.bls.verify', side_effect=mock_bls_verify)
    mocker.patch('py_ecc.bls.verify_multiple', side_effect=mock_bls_verify_multiple)


def get_test_case(file_names):
    all_test_cases = []
    for file_name in file_names:
        with open(BASE_FIXTURE_PATH + '/' + file_name, 'U') as f:
            # TODO: `proof_of_possession` is used in v0.5.1 spec and will be renamed to `signature`
            # Trinity renamed it ahead due to py-ssz signing_root requirements
            new_text = f.read().replace('proof_of_possession', 'signature')
            try:
                data = yaml.load(new_text)
                all_test_cases += data['test_cases']
            except yaml.YAMLError as exc:
                print(exc)
    return all_test_cases


test_cases = get_test_case(FILE_NAMES)


@pytest.mark.parametrize("test_case", test_cases)
def test_state(base_db, test_case):
    test_name = test_case['name']
    if test_name == 'test_transfer':
        print('skip')
    else:
        execute_state_transtion(test_case, base_db)


def generate_config_by_dict(dict_config):
    dict_config['DEPOSIT_CONTRACT_ADDRESS'] = b'\x00' * 20
    for key in list(dict_config):
        if 'DOMAIN_' in key in key:
            # DOMAIN is defined in SignatureDomain
            dict_config.pop(key, None)
    return Eth2Config(**dict_config)


def execute_state_transtion(test_case, base_db):
    test_name = test_case['name']
    dict_config = test_case['config']
    verify_signatures = test_case['verify_signatures']
    dict_initial_state = test_case['initial_state']
    dict_blocks = test_case['blocks']
    dict_expected_state = test_case['expected_state']

    # TODO: make it case by case
    assert verify_signatures is False

    print(f"[{test_name}]")

    # Set config
    config = generate_config_by_dict(dict_config)

    # Set Vector fields
    override_vector_lengths(config)

    # Set pre_state
    pre_state = from_formatted_dict(dict_initial_state, BeaconState)

    # Set blocks
    blocks = ()
    for dict_block in dict_blocks:
        block = from_formatted_dict(dict_block, SerenityBeaconBlock)
        blocks += (block,)

    sm_class = SerenityStateMachine.configure(
        __name__='SerenityStateMachineForTesting',
        config=config,
    )
    chaindb = BeaconChainDB(base_db)

    post_state = pre_state.copy()
    for block in blocks:
        sm = sm_class(chaindb, None, post_state)
        post_state, _ = sm.import_block(block)

    # Use dict diff, easier to see the diff
    dict_post_state = to_formatted_dict(post_state, BeaconState)

    for key, value in dict_expected_state.items():
        if isinstance(value, list):
            value = tuple(value)
        assert dict_post_state[key] == value
