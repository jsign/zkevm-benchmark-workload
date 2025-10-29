//! Generate fixtures for zkEVM benchmarking tool

use alloy_genesis::ChainConfig;
use async_trait::async_trait;
use ef_tests::{
    Case,
    cases::blockchain_test::{BlockchainTestCase, ExecutionWitnesses},
    models::BlockchainTest,
};
use rayon::prelude::*;
use reth_chainspec::ChainSpec;
use reth_ethereum_primitives::Block;
use serde::{Deserialize, Serialize};
use std::{
    path::{Path, PathBuf},
    process::Command,
};
use tracing::error;
use walkdir::{DirEntry, WalkDir};

use crate::{
    Fixture, FixtureGenerator, Result, StatelessValidationFixture, WitnessGeneratorError,
    WitnessType,
};
use reth_stateless::{ExecutionWitness, GenericStatelessInput, flat_witness::FlatExecutionWitness};

/// Witness generator that produces `BlockAndWitness` fixtures for execution-spec-test fixtures.
#[derive(Debug, Clone, Default)]
pub struct ExecSpecTestBlocksAndWitnessBuilder {
    input_folder: Option<PathBuf>,
    tag: Option<String>,
    include: Option<Vec<String>>,
    exclude: Option<Vec<String>>,
}

impl ExecSpecTestBlocksAndWitnessBuilder {
    const TEMP_EEST_FIXTURES_PATH: &str = "./zkevm-fixtures";

    /// Sets the tag for the execution-spec-test fixtures.
    pub fn with_tag(mut self, tag: String) -> Self {
        self.tag = Some(tag);
        self
    }

    /// Sets the input folder for the execution-spec-test fixtures.
    /// Returns an error if the path doesn't exist or isn't a directory.
    pub fn with_input_folder(mut self, path: PathBuf) -> Result<Self> {
        if !path.exists() {
            return Err(WitnessGeneratorError::EestPathNotFound(
                path.display().to_string(),
            ));
        }
        if !path.is_dir() {
            return Err(WitnessGeneratorError::EestPathNotDirectory(
                path.display().to_string(),
            ));
        }
        let canonical_path =
            path.canonicalize()
                .map_err(|e| WitnessGeneratorError::PathResolutionError {
                    path: path.display().to_string(),
                    source: e,
                })?;

        self.input_folder = Some(canonical_path);
        Ok(self)
    }

    /// Includes only test names that contain the provided strings.
    pub fn with_includes(mut self, includes: Vec<String>) -> Self {
        self.include = Some(includes);
        self
    }

    /// Excludes all test names that contain the provided strings.
    pub fn with_excludes(mut self, exclude: Vec<String>) -> Self {
        self.exclude = Some(exclude);
        self
    }

    /// Builds the `ExecSpecTestBlocksAndWitnesses` instance.
    pub fn build<WS: WitnessesSelector>(self) -> Result<ExecSpecTestBlocksAndWitnesses<WS>> {
        let input_folder = self.input_folder;
        let tag = self.tag;
        let include = self.include.unwrap_or_default();
        let exclude = self.exclude.unwrap_or_default();

        // delete_eest_folder indicates if the EEST folder will be automatically deleted after witness generation.
        // If this folder was explicitly provided, we do not delete it.
        let (directory_path, delete_eest_folder) = if let Some(input_folder) = input_folder {
            (input_folder, false)
        } else {
            let mut cmd = Command::new("./scripts/download-and-extract-fixtures.sh");
            if let Some(tag) = tag {
                cmd.arg(tag);
            }
            let output = cmd
                .output()
                .map_err(WitnessGeneratorError::DownloadScriptExecutionError)?;

            if !output.status.success() {
                return Err(WitnessGeneratorError::DownloadScriptFailed(
                    String::from_utf8_lossy(&output.stderr).to_string(),
                ));
            }
            (PathBuf::from(&Self::TEMP_EEST_FIXTURES_PATH), true)
        };

        Ok(ExecSpecTestBlocksAndWitnesses {
            directory_path,
            include,
            exclude,
            delete_eest_folder,
            _marker: std::marker::PhantomData,
        })
    }
}

/// Witness generator that produces `BlockAndWitness` fixtures for EEST fixtures.
#[derive(Debug, Clone)]
pub struct ExecSpecTestBlocksAndWitnesses<WS: WitnessesSelector> {
    directory_path: PathBuf,
    include: Vec<String>,
    exclude: Vec<String>,
    delete_eest_folder: bool,

    _marker: std::marker::PhantomData<WS>,
}

impl<WS: WitnessesSelector> Drop for ExecSpecTestBlocksAndWitnesses<WS> {
    fn drop(&mut self) {
        if self.delete_eest_folder && self.directory_path.exists() {
            match std::fs::remove_dir_all(&self.directory_path) {
                Ok(_) => {}
                Err(e) => error!(
                    "Failed to remove directory {}: {}",
                    self.directory_path.display(),
                    e
                ),
            }
        }
    }
}

/// Trait for selecting witnesses from execution-spec-test cases.
pub trait WitnessesSelector: Send + Sync {
    /// The target type produced by the witness selector.
    type Target: Serialize + for<'de> Deserialize<'de> + Send + Sync + 'static;

    /// Selects the appropriate witness type from the provided execution witnesses.
    fn select_witness(
        block: Block,
        witnesses: ExecutionWitnesses,
        chain_config: ChainConfig,
    ) -> GenericStatelessInput<Self::Target>;
}

/// Selects trie-based witnesses for stateless execution.
#[derive(Debug)]
pub struct TrieWitnessSelector;

impl WitnessesSelector for TrieWitnessSelector {
    type Target = ExecutionWitness;

    fn select_witness(
        block: Block,
        witnesses: ExecutionWitnesses,
        chain_config: ChainConfig,
    ) -> GenericStatelessInput<ExecutionWitness> {
        GenericStatelessInput::<ExecutionWitness> {
            block,
            witness: witnesses.trie,
            chain_config,
        }
    }
}

/// Selects flatdb based witnesses for stateless execution.
#[derive(Debug)]
pub struct FlatWitnessSelector;

impl WitnessesSelector for FlatWitnessSelector {
    type Target = FlatExecutionWitness;

    fn select_witness(
        block: Block,
        witnesses: ExecutionWitnesses,
        chain_config: ChainConfig,
    ) -> GenericStatelessInput<FlatExecutionWitness> {
        GenericStatelessInput::<FlatExecutionWitness> {
            block,
            witness: witnesses.flatdb,
            chain_config,
        }
    }
}

#[async_trait]
impl<WS: WitnessesSelector> FixtureGenerator for ExecSpecTestBlocksAndWitnesses<WS> {
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
    async fn generate_to_path(&self, path: &Path, witness_type: WitnessType) -> Result<usize> {
        let bws = self.generate(witness_type).await?;
        for bw in &bws {
            let output_path = path.join(format!("{}.json", bw.name()));
            let mut buf = Vec::new();
            let mut serializer = serde_json::Serializer::pretty(&mut buf);
            erased_serde::serialize(bw.as_ref(), &mut serializer).map_err(|e| {
                WitnessGeneratorError::FixtureSerializationError {
                    name: bw.name().to_owned(),
                    source: e,
                }
            })?;

            std::fs::write(&output_path, buf).map_err(|e| {
                WitnessGeneratorError::FixtureWriteError {
                    path: output_path.display().to_string(),
                    source: e,
                }
            })?;
        }
        Ok(bws.len())
    }
}

impl<WS: WitnessesSelector> ExecSpecTestBlocksAndWitnesses<WS> {
    // Generates blocks and witnesses from the EEST fixtures located in the specified directory,
    // filtering by the provided include and exclude patterns.
    async fn generate(&self, witness_type: WitnessType) -> Result<Vec<Box<dyn Fixture>>> {
        let suite_path = self.directory_path.join("fixtures/blockchain_tests");

        if !suite_path.exists() {
            return Err(WitnessGeneratorError::TestSuitePathNotFound(
                suite_path.display().to_string(),
            ));
        }

        let test_file_paths = find_all_files_with_extension(&suite_path, ".json");
        let mut tests: Vec<(String, BlockchainTest)> = Vec::new();
        for path in test_file_paths {
            let test_case = BlockchainTestCase::load(&path).map_err(|e| {
                WitnessGeneratorError::TestCaseLoadError {
                    path: path.display().to_string(),
                    source: Box::new(e) as Box<dyn std::error::Error + Send + Sync>,
                }
            })?;

            let file_tests: Vec<(String, BlockchainTest)> = test_case
                .tests
                .into_iter()
                .map(|(name, case)| {
                    (
                        name.split('/').next_back().unwrap_or(&name).to_string(),
                        case,
                    )
                })
                .filter(|(name, _)| !self.exclude.iter().any(|filter| name.contains(filter)))
                .filter(|(name, _)| self.include.iter().all(|f| name.contains(f)))
                .collect();
            tests.extend(file_tests);
        }

        let bws = tests
            .par_iter()
            .map(|(name, case)| {
                let chain_spec: ChainSpec = case.network.into();
                let chain_config = chain_spec.genesis.config;
                let (recovered_block, witnesses) = BlockchainTestCase::run_single_case(name, case)
                    .map_err(|e| WitnessGeneratorError::TestCaseExecutionError {
                        source: Box::new(e) as Box<dyn std::error::Error + Send + Sync>,
                    })?
                    .into_iter()
                    .next_back()
                    .ok_or_else(|| WitnessGeneratorError::NoTargetBlock(name.clone()))?;
                let stateless_input =
                    WS::select_witness(recovered_block.into_block(), witnesses, chain_config);
                let success = case
                    .blocks
                    .iter()
                    .next_back()
                    .unwrap()
                    .expect_exception
                    .is_none();
                Ok(StatelessValidationFixture {
                    name: name.clone(),
                    stateless_input,
                    success,
                })
            })
            .collect::<Result<Vec<_>>>()?;

        Ok(bws
            .into_iter()
            .map(|f| Box::new(f) as Box<dyn Fixture>)
            .collect())
    }
}

/// Recursively finds all files within `path` that end with `extension`.
// This function was copied from `ef-tests`
fn find_all_files_with_extension(path: &Path, extension: &str) -> Vec<PathBuf> {
    WalkDir::new(path)
        .into_iter()
        .filter_map(std::result::Result::ok)
        .filter(|e| e.file_name().to_string_lossy().ends_with(extension))
        .map(DirEntry::into_path)
        .collect()
}
