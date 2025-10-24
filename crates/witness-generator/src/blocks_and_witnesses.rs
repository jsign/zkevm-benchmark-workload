use std::path::PathBuf;
use std::{fs, io, path::Path};

use alloy_genesis::ChainConfig;
use anyhow::anyhow;
use anyhow::{Context, Result, bail};
use async_trait::async_trait;
use ef_tests::{
    Case,
    cases::blockchain_test::{BlockchainTestCase, ExecutionWitnesses},
    models::BlockchainTest,
};
use rayon::iter::{IntoParallelRefIterator, ParallelIterator};
use reth_chainspec::ChainSpec;
use reth_ethereum_primitives::Block;
use reth_primitives_traits::RecoveredBlock;
use reth_stateless::{StatelessExecutionInput, StatelessInput};
use serde::{Deserialize, Serialize};
use thiserror::Error;
use walkdir::{DirEntry, WalkDir};

pub type BlockAndTrieWitness = BlockAndWitness<StatelessInput>;
pub type BlockAndFlatWitness = BlockAndWitness<StatelessExecutionInput>;

/// Represents a named collection of block/witness pairs for a specific Ethereum test case.
///
/// This structure typically corresponds to a single blockchain test case from the
/// `ethereum/tests` fixtures (however we are using `zkevm-fixtures`)
///  containing all the sequential block transitions within that test.
#[derive(Debug, Serialize, Deserialize)]
pub struct BlockAndWitness<T> {
    /// Name of the blockchain test case (e.g., "`ModExpAttackContract`").
    pub name: String,
    /// The block and witness pair for the test case.
    pub block_and_witness: T,
    /// Whether the stateless block validation is successful.
    pub success: bool,
}

/// Errors that can occur during serialization or deserialization of `BlocksAndWitnesses`.
#[derive(Error, Debug)]
pub enum BwError {
    /// Serde JSON (de)serialization error.
    #[error("serde JSON (de)serialization error: {0}")]
    Serde(#[from] serde_json::Error),

    /// Error during file system I/O operations.
    #[error("I/O error: {0}")]
    Io(#[from] io::Error),
}

impl<T: Serialize + for<'de> Deserialize<'de>> BlockAndWitness<T> {
    /// Serializes a list of `BlockAndWitness` test cases to a JSON pretty-printed string.
    ///
    /// # Errors
    ///
    /// Returns `BwError::Serde` if JSON serialization fails.
    pub fn to_json(items: &[Self]) -> Result<String, BwError> {
        serde_json::to_string_pretty(items).map_err(BwError::from)
    }

    /// Deserializes a list of `BlockAndWitness` test cases from a JSON string.
    ///
    /// Assumes the input JSON was produced by [`Self::to_json`].
    ///
    /// # Errors
    ///
    /// Returns `BwError::Serde` if JSON deserialization fails.
    pub fn from_json(json: &str) -> Result<Vec<Self>, BwError> {
        serde_json::from_str(json).map_err(BwError::from)
    }

    /// Serializes `items` to pretty-printed JSON and writes them to `path`.
    ///
    /// The file is created if it does not exist and truncated if it does.
    /// Parent directories are *not* created automatically.
    ///
    /// # Errors
    ///
    /// Returns `BwError::Io` if any filesystem operation fails.
    /// Returns `BwError::Serde` if JSON serialization fails.
    pub fn to_path<P: AsRef<Path>>(path: P, items: &[Self]) -> Result<(), BwError> {
        let json = Self::to_json(items)?;
        fs::write(path, json).map_err(BwError::Io)?;
        Ok(())
    }

    /// Reads the file at `path` and deserializes a `Vec<BlocksAndWitnesses>` from its JSON content.
    ///
    /// Assumes the file contains JSON compatible with [`Self::from_json`].
    ///
    /// # Errors
    ///
    /// Returns `BwError::Io` if reading the file fails.
    /// Returns `BwError::Serde` if JSON deserialization fails.
    pub fn from_path<P: AsRef<Path>>(path: P) -> Result<Vec<Self>, BwError> {
        let path = path.as_ref();
        let contents = fs::read_to_string(path).map_err(BwError::Io)?;
        Self::from_json(&contents)
    }
}

/// Trait for generating blocks and witnesses.
///
/// Implementors of this trait provide different strategies for generating
/// `BlocksAndWitnesses` collections, such as from test fixtures or RPC endpoints.
#[async_trait]
pub trait WitnessGenerator<T>
where
    T: Serialize + Send + Sync,
{
    // Generates blocks and witnesses from the EEST fixtures located in the specified directory,
    // filtering by the provided include and exclude patterns.
    async fn generate(&self) -> Result<Vec<BlockAndWitness<T>>>;

    /// Generates `BlockAndWitness` fixtures from EEST test cases and writes them to the specified path.
    ///
    /// This method processes all matching EEST test cases, generates the corresponding
    /// witness data, and writes each fixture as a separate JSON file in the output directory.
    ///
    /// # Arguments
    /// * `path` - The directory path where JSON fixture files will be written
    ///
    /// # Returns
    /// The number of fixture files successfully generated and written
    ///
    /// # Errors
    /// Returns an error if fixture generation fails, serialization fails, or file writing fails.
    async fn generate_to_path(&self, path: &Path) -> Result<usize>;
}
