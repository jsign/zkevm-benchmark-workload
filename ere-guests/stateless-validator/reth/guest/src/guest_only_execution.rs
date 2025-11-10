//! Abstracted guest program

use alloc::sync::Arc;

use ere_io_serde::IoSerde;
use k256::sha2::{Digest, Sha256};
use reth_chainspec::ChainSpec;
use reth_evm_ethereum::EthEvmConfig;
use reth_guest_io::{io_serde, Input};
use reth_primitives_traits::Block;
use reth_stateless::{
    flat_witness::{
        bincode::{CacheBincode, HashedPostStateBincode},
        FlatExecutionWitness,
    },
    validation::stateless_validation_with_flatdb,
    Genesis,
};
use reth_trie_common::{HashedPostState, KeccakKeyHasher};

use crate::sdk::{ScopeMarker, SDK};

/// Main entry point for the guest program.
pub fn ethereum_guest<S: SDK>() {
    S::cycle_scope(ScopeMarker::Start, "read_input");
    let input: Input<FlatExecutionWitness> = io_serde()
        .deserialize(&S::read_input())
        .expect("Failed to read input");

    let genesis = Genesis {
        config: input.stateless_input.chain_config.clone(),
        ..Default::default()
    };
    let chain_spec: Arc<ChainSpec> = Arc::new(genesis.into());
    let evm_config = EthEvmConfig::new(chain_spec.clone());
    S::cycle_scope(ScopeMarker::End, "read_input");

    S::cycle_scope(ScopeMarker::Start, "public_inputs_preparation_base");
    let header = input.stateless_input.block.header().clone();
    let parent_hash = input.stateless_input.block.parent_hash;
    S::cycle_scope(ScopeMarker::End, "public_inputs_preparation_base");
    S::cycle_scope(
        ScopeMarker::Start,
        "public_inputs_preparation_flatdb_serialization",
    );
    // let flatdb_serialized = bincode_v2::serde::encode_to_vec(
    //     CacheBincode::from(input.stateless_input.witness.state.clone()),
    //     bincode_v2::config::legacy(),
    // )
    // .unwrap();
    S::cycle_scope(
        ScopeMarker::End,
        "public_inputs_preparation_flatdb_serialization",
    );
    S::cycle_scope(
        ScopeMarker::Start,
        "public_inputs_preparation_flatdb_hashing",
    );
    // let flatdb_hash: [u8; 32] = Sha256::digest(flatdb_serialized).into();
    // S::cycle_scope(ScopeMarker::End, "public_inputs_preparation_flatdb_hashing");

    S::cycle_scope(ScopeMarker::Start, "validation");
    let res = stateless_validation_with_flatdb::<_, _>(
        input.stateless_input.block,
        input.public_keys,
        input.stateless_input.witness,
        chain_spec,
        evm_config,
    );
    S::cycle_scope(ScopeMarker::End, "validation");

    match res {
        Ok((block_hash, output)) => {
            S::cycle_scope(
                ScopeMarker::Start,
                "public_inputs_preparation_poststate_generation",
            );
            // let post_state: HashedPostStateBincode =
            //     HashedPostState::from_bundle_state::<KeccakKeyHasher>(&output.state.state).into();
            S::cycle_scope(
                ScopeMarker::End,
                "public_inputs_preparation_poststate_generation",
            );
            S::cycle_scope(
                ScopeMarker::Start,
                "public_inputs_preparation_poststate_serialization",
            );
            // let post_state_serialized =
            //     bincode_v2::serde::encode_to_vec(post_state, bincode_v2::config::legacy()).unwrap();
            S::cycle_scope(
                ScopeMarker::End,
                "public_inputs_preparation_poststate_serialization",
            );
            S::cycle_scope(
                ScopeMarker::Start,
                "public_inputs_preparation_poststate_hashing",
            );
            // let post_state_hash: [u8; 32] = Sha256::digest(post_state_serialized).into();
            S::cycle_scope(
                ScopeMarker::End,
                "public_inputs_preparation_poststate_hashing",
            );

            S::cycle_scope(ScopeMarker::Start, "commit_public_inputs");
            let public_inputs = (
                block_hash.0,
                parent_hash.0,
                // flatdb_hash,
                // post_state_hash,
                true,
            );
            let public_inputs_hash: [u8; 32] = Sha256::digest(
                bincode_v2::serde::encode_to_vec(public_inputs, bincode_v2::config::legacy())
                    .unwrap(),
            )
            .into();
            S::commit_output(public_inputs_hash);
            S::cycle_scope(ScopeMarker::End, "commit_public_inputs");
        }
        Err(_err) => {
            let public_inputs = (header.hash_slow().0, parent_hash.0, false);
            let public_inputs_hash: [u8; 32] = Sha256::digest(
                bincode_v2::serde::encode_to_vec(public_inputs, bincode_v2::config::legacy())
                    .unwrap(),
            )
            .into();
            S::commit_output(public_inputs_hash);
        }
    }
}
