//! CLI definitions for the zkVM benchmarker

use std::{path::PathBuf, str::FromStr};

use anyhow::{Result, bail};
use benchmark_runner::{runner::Action, stateless_validator};
use clap::{Parser, Subcommand, ValueEnum};
use ere_dockerized::ErezkVM;
use ere_zkvm_interface::ProverResourceType;

/// Command line interface for the zkVM benchmarker
#[derive(Parser)]
#[command(name = "zkvm-benchmarker")]
#[command(about = "Benchmark different Ere compatible zkVMs")]
#[command(version)]
#[derive(Debug)]
pub struct Cli {
    /// Resource type for proving
    #[arg(short, long, value_enum, default_value = "cpu")]
    pub resource: Resource,

    /// Action to perform
    #[arg(short, long, value_enum, default_value = "execute")]
    pub action: BenchmarkAction,

    /// zkVM instances to benchmark
    #[arg(long, required(true), value_parser = <ErezkVM as std::str::FromStr>::from_str)]
    pub zkvms: Vec<ErezkVM>,

    /// Rerun the benchmarks even if the output folder already contains results
    #[arg(long, default_value_t = false)]
    pub force_rerun: bool,

    /// Guest program to benchmark
    #[command(subcommand)]
    pub guest_program: GuestProgramCommand,

    /// Output folder for benchmark results
    #[arg(short, long, default_value = "zkevm-metrics")]
    pub output_folder: PathBuf,
}

/// Subcommands for different guest programs
#[derive(Subcommand, Clone, Debug)]
pub enum GuestProgramCommand {
    /// Ethereum Stateless Validator
    StatelessValidator {
        /// Input folder for benchmark fixtures
        #[arg(short, long, default_value = "zkevm-fixtures-input")]
        input_folder: PathBuf,
        /// Execution client to benchmark
        #[arg(short, long)]
        execution_client: ExecutionClient,
        /// Mode of the stateless validator
        #[arg(short, long, default_value = "execution-and-storage")]
        mode: StatelessValidatorMode,
    },
    /// Empty program
    EmptyProgram,

    /// Block encoding length
    BlockEncodingLength {
        /// Input folder for benchmark fixtures
        #[arg(short, long, default_value = "zkevm-fixtures-input")]
        input_folder: PathBuf,

        /// Number of times to loop the benchmark
        #[arg(long)]
        loop_count: u16,

        /// Encoding format
        #[arg(short, long, value_enum)]
        format: BlockEncodingFormat,
    },
}

/// Stateless validator modes
#[derive(Debug, Clone, ValueEnum)]
pub enum StatelessValidatorMode {
    /// Validate both execution and storage
    ExecutionAndStorage,
    /// Validate only execution
    OnlyExecution,
}

/// Encoding formats for block encoding length program
#[derive(Debug, Clone, ValueEnum)]
pub enum BlockEncodingFormat {
    /// RLP encoding
    Rlp,
    /// SSZ encoding
    Ssz,
}

/// Execution clients for the stateless validator
#[derive(Debug, Copy, Clone, ValueEnum)]
pub enum ExecutionClient {
    /// Reth execution client
    Reth,
    /// Ethrex execution client
    Ethrex,
}

impl ExecutionClient {
    /// Get the guest relative path for the execution client
    pub fn guest_rel_path(&self, mode: &StatelessValidatorMode) -> Result<PathBuf> {
        let path = match (self, mode) {
            (Self::Reth, StatelessValidatorMode::ExecutionAndStorage) => "stateless-validator/reth",
            (Self::Ethrex, StatelessValidatorMode::ExecutionAndStorage) => {
                "stateless-validator/ethrex"
            }
            (Self::Reth, StatelessValidatorMode::OnlyExecution) => {
                "stateless-validator-execution/reth"
            }
            (Self::Ethrex, StatelessValidatorMode::OnlyExecution) => {
                bail!("Ethrex client is not supported for OnlyExecution mode")
            }
        };
        Ok(PathBuf::from_str(path).unwrap())
    }
}

/// Prover resource types
#[derive(Debug, Clone, ValueEnum)]
pub enum Resource {
    /// CPU resource
    Cpu,
    /// GPU resource
    Gpu,
}

/// Benchmark actions
#[derive(Debug, Clone, ValueEnum)]
pub enum BenchmarkAction {
    /// Only do zkVM execution
    Execute,
    /// Create a zkVM proof
    Prove,
}

impl From<Resource> for ProverResourceType {
    fn from(resource: Resource) -> Self {
        match resource {
            Resource::Cpu => Self::Cpu,
            Resource::Gpu => Self::Gpu,
        }
    }
}

impl From<BenchmarkAction> for Action {
    fn from(action: BenchmarkAction) -> Self {
        match action {
            BenchmarkAction::Execute => Self::Execute,
            BenchmarkAction::Prove => Self::Prove,
        }
    }
}

impl From<BlockEncodingFormat> for block_encoding_length_io::BlockEncodingFormat {
    fn from(format: BlockEncodingFormat) -> Self {
        match format {
            BlockEncodingFormat::Rlp => Self::Rlp,
            BlockEncodingFormat::Ssz => Self::Ssz,
        }
    }
}

impl From<ExecutionClient> for stateless_validator::ExecutionClient {
    fn from(client: ExecutionClient) -> Self {
        match client {
            ExecutionClient::Reth => Self::Reth,
            ExecutionClient::Ethrex => Self::Ethrex,
        }
    }
}

impl From<StatelessValidatorMode> for stateless_validator::StatelessValidatorMode {
    fn from(mode: StatelessValidatorMode) -> Self {
        match mode {
            StatelessValidatorMode::ExecutionAndStorage => Self::ExecutionAndStorage,
            StatelessValidatorMode::OnlyExecution => Self::OnlyExecution,
        }
    }
}
