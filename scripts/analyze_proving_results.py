#!/usr/bin/env python3
"""
zkVM Proving Results Analysis Script

This script analyzes zkVM proving results from benchmark runs and generates
comprehensive visualizations and statistics for comparing different guest
program configurations.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

# Set style for professional-looking charts
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 7)
plt.rcParams['font.size'] = 10


@dataclass
class ExecutionMetrics:
    """Metrics from execution runs"""
    block_number: int
    total_num_cycles: int
    region_cycles: Dict[str, int]
    execution_duration_ms: float
    block_used_gas: int


@dataclass
class ProvingMetrics:
    """Metrics from proving runs"""
    block_number: int
    proof_size: int
    proving_time_ms: int
    block_used_gas: int


@dataclass
class CombinedMetrics:
    """Combined execution and proving metrics"""
    block_number: int
    total_num_cycles: int
    proving_time_ms: int
    proving_time_per_cycle: float  # ms per million cycles


class ZKVMAnalyzer:
    """Main analyzer class for zkVM proving results"""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.results = {}

    def load_execution_data(self, folder_path: Path, guest_type: str, zkvm: str) -> List[ExecutionMetrics]:
        """Load execution metrics from JSON files"""
        metrics = []
        reth_path = folder_path / "reth" / zkvm

        if not reth_path.exists():
            print(f"Warning: Path does not exist: {reth_path}")
            return metrics

        for json_file in sorted(reth_path.glob("rpc_block_*.json")):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)

                # Extract block number from filename
                block_num = int(json_file.stem.split('_')[-1])

                # Check if execution was successful
                if 'execution' not in data or 'success' not in data['execution']:
                    print(f"Warning: Skipping {json_file} - no successful execution data")
                    continue

                exec_data = data['execution']['success']

                # Calculate execution duration in milliseconds
                duration_ms = exec_data['execution_duration']['secs'] * 1000
                duration_ms += exec_data['execution_duration']['nanos'] / 1_000_000

                metrics.append(ExecutionMetrics(
                    block_number=block_num,
                    total_num_cycles=exec_data['total_num_cycles'],
                    region_cycles=exec_data.get('region_cycles', {}),
                    execution_duration_ms=duration_ms,
                    block_used_gas=data['metadata']['block_used_gas']
                ))
            except Exception as e:
                print(f"Error loading {json_file}: {e}")

        return metrics

    def load_proving_data(self, folder_path: Path, guest_type: str, zkvm: str) -> List[ProvingMetrics]:
        """Load proving metrics from JSON files"""
        metrics = []
        reth_path = folder_path / "reth" / zkvm

        if not reth_path.exists():
            print(f"Warning: Path does not exist: {reth_path}")
            return metrics

        for json_file in sorted(reth_path.glob("rpc_block_*.json")):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)

                # Extract block number from filename
                block_num = int(json_file.stem.split('_')[-1])

                # Check if proving was successful
                if 'proving' not in data or 'success' not in data['proving']:
                    print(f"Warning: Skipping {json_file} - no successful proving data")
                    continue

                proving_data = data['proving']['success']

                metrics.append(ProvingMetrics(
                    block_number=block_num,
                    proof_size=proving_data['proof_size'],
                    proving_time_ms=proving_data['proving_time_ms'],
                    block_used_gas=data['metadata']['block_used_gas']
                ))
            except Exception as e:
                print(f"Error loading {json_file}: {e}")

        return metrics

    def combine_metrics(self, exec_metrics: List[ExecutionMetrics],
                       proving_metrics: List[ProvingMetrics]) -> List[CombinedMetrics]:
        """Combine execution and proving metrics by block number"""
        combined = []

        # Create lookup dict for proving metrics
        proving_dict = {m.block_number: m for m in proving_metrics}

        for exec_m in exec_metrics:
            if exec_m.block_number in proving_dict:
                prov_m = proving_dict[exec_m.block_number]

                # Calculate proving time per million cycles
                proving_time_per_mcycle = (prov_m.proving_time_ms / exec_m.total_num_cycles) * 1_000_000

                combined.append(CombinedMetrics(
                    block_number=exec_m.block_number,
                    total_num_cycles=exec_m.total_num_cycles,
                    proving_time_ms=prov_m.proving_time_ms,
                    proving_time_per_cycle=proving_time_per_mcycle
                ))

        return combined

    def analyze_with_checks(self, output_dir: Path):
        """Analyze with-checks benchmark data"""
        print("\n=== Analyzing WITH-CHECKS Data ===")

        base_path = self.base_path / "zkevm-metrics-benchs-with-checks"

        for zkvm in ["sp1-v5.2.1", "zisk-v0.13.0"]:
            zkvm_short = zkvm.split('-')[0]  # "sp1" or "zisk"
            print(f"\n--- Analyzing {zkvm_short.upper()} ---")

            # Create output directory for this zkVM
            zkvm_output = output_dir / f"with_checks_{zkvm_short}"
            zkvm_output.mkdir(parents=True, exist_ok=True)

            # Guest program types with different names for execution vs proving
            # Format: (execution_folder_name, proving_folder_name, display_label)
            guest_configs = [
                ("zkevm-metrics-bench-execution-only", "zkevm-metrics-bench-execution-only", "Execution-Only"),
                ("zkevm-metrics-bench-full-validation", "zkevm-metrics-bench-full-validation", "Full-Validation"),
                ("zkevm-metrics-bench-pre-post-state", "zkevm-metrics-bench-pre-post-state-check", "Pre/Post-State")
            ]

            # Collect data
            all_data = {}

            for exec_name, prov_name, label in guest_configs:
                exec_path = base_path / "execution" / exec_name
                prov_path = base_path / "proving" / prov_name

                exec_metrics = self.load_execution_data(exec_path, exec_name, zkvm)
                prov_metrics = self.load_proving_data(prov_path, prov_name, zkvm)

                # Use a consistent key for lookups
                key = label.lower().replace('/', '_').replace(' ', '_').replace('-', '_')

                all_data[key] = {
                    'exec': exec_metrics,
                    'prov': prov_metrics,
                    'label': label
                }

            # Generate visualizations
            self.plot_proving_times_comparison(all_data, zkvm_output / "proving_times.png", zkvm_short)
            self.plot_total_cycles_comparison(all_data, zkvm_output / "total_cycles.png", zkvm_short)

            # Generate pie charts for SP1 region cycles
            if zkvm_short == "sp1":
                self.plot_region_cycles_pie(all_data, zkvm_output, "with_checks")

            # Generate markdown table
            self.generate_markdown_table(all_data, zkvm_output / "statistics.md",
                                        zkvm_short, include_time_per_cycle=False)

    def analyze_without_checks(self, output_dir: Path):
        """Analyze without-checks benchmark data"""
        print("\n=== Analyzing WITHOUT-CHECKS Data ===")

        base_path = self.base_path / "zkevm-metrics-benchs-without-checks"

        for zkvm in ["sp1-v5.2.1", "zisk-v0.13.0"]:
            zkvm_short = zkvm.split('-')[0]  # "sp1" or "zisk"
            print(f"\n--- Analyzing {zkvm_short.upper()} ---")

            # Create output directory for this zkVM
            zkvm_output = output_dir / f"without_checks_{zkvm_short}"
            zkvm_output.mkdir(parents=True, exist_ok=True)

            # Guest program types with different names for execution vs proving
            # Format: (execution_folder_name, proving_folder_name, display_label)
            guest_configs = [
                ("zkevm-metrics-bench-execution-only", "zkevm-metrics-bench-execution-only", "Execution-Only"),
                ("zkevm-metrics-pre-post-state", "zkevm-metrics-bench-pre-post-state-check", "Pre/Post-State")
            ]

            # Collect data
            all_data = {}

            for exec_name, prov_name, label in guest_configs:
                exec_path = base_path / "execution" / exec_name
                prov_path = base_path / "proving" / prov_name

                exec_metrics = self.load_execution_data(exec_path, exec_name, zkvm)
                prov_metrics = self.load_proving_data(prov_path, prov_name, zkvm)

                # Use a consistent key for lookups
                key = label.lower().replace('/', '_').replace(' ', '_').replace('-', '_')

                all_data[key] = {
                    'exec': exec_metrics,
                    'prov': prov_metrics,
                    'label': label
                }

            # Generate visualizations
            self.plot_proving_times_comparison(all_data, zkvm_output / "proving_times.png", zkvm_short)
            self.plot_total_cycles_comparison(all_data, zkvm_output / "total_cycles.png", zkvm_short)

            # Generate ratio comparison
            self.plot_proving_time_ratio(all_data, zkvm_output / "proving_time_ratio.png", zkvm_short)

            # Generate proving time per cycle chart
            self.plot_time_per_cycle(all_data, zkvm_output / "time_per_cycle.png", zkvm_short)

            # Generate pie charts for SP1 region cycles
            if zkvm_short == "sp1":
                self.plot_region_cycles_pie(all_data, zkvm_output, "without_checks")

            # Generate markdown table
            self.generate_markdown_table(all_data, zkvm_output / "statistics.md",
                                        zkvm_short, include_time_per_cycle=True)

    def plot_proving_times_comparison(self, all_data: Dict, output_path: Path, zkvm: str):
        """Create bar chart comparing average proving times"""
        fig, ax = plt.subplots(figsize=(10, 6))

        labels = []
        avg_times = []
        std_times = []

        for guest_type, data in all_data.items():
            if not data['prov']:
                continue

            times = [m.proving_time_ms for m in data['prov']]
            labels.append(data['label'])
            avg_times.append(np.mean(times))
            std_times.append(np.std(times))

        x = np.arange(len(labels))
        bars = ax.bar(x, avg_times, yerr=std_times, capsize=5,
                     color=['#2ecc71', '#3498db', '#e74c3c'][:len(labels)], alpha=0.8)

        ax.set_xlabel('Guest Program Type', fontsize=12, fontweight='bold')
        ax.set_ylabel('Average Proving Time (ms)', fontsize=12, fontweight='bold')
        ax.set_title(f'{zkvm.upper()} - Average Proving Time Comparison',
                    fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(labels)

        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{height/1000:.1f}s',
                   ha='center', va='bottom', fontweight='bold')

        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"Saved: {output_path}")

    def plot_total_cycles_comparison(self, all_data: Dict, output_path: Path, zkvm: str):
        """Create bar chart comparing average total cycles"""
        fig, ax = plt.subplots(figsize=(10, 6))

        labels = []
        avg_cycles = []
        std_cycles = []

        for guest_type, data in all_data.items():
            if not data['exec']:
                continue

            cycles = [m.total_num_cycles for m in data['exec']]
            labels.append(data['label'])
            avg_cycles.append(np.mean(cycles))
            std_cycles.append(np.std(cycles))

        x = np.arange(len(labels))
        bars = ax.bar(x, avg_cycles, yerr=std_cycles, capsize=5,
                     color=['#9b59b6', '#f39c12', '#1abc9c'][:len(labels)], alpha=0.8)

        ax.set_xlabel('Guest Program Type', fontsize=12, fontweight='bold')
        ax.set_ylabel('Average Total Cycles', fontsize=12, fontweight='bold')
        ax.set_title(f'{zkvm.upper()} - Average Total Cycles Comparison',
                    fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(labels)

        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{height/1e6:.1f}M',
                   ha='center', va='bottom', fontweight='bold')

        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"Saved: {output_path}")

    def plot_region_cycles_pie(self, all_data: Dict, output_dir: Path, variant: str):
        """Create pie charts for region cycle breakdown (SP1 only)"""
        for guest_type, data in all_data.items():
            if not data['exec'] or not data['exec'][0].region_cycles:
                continue

            # Aggregate region cycles across all blocks
            region_totals = defaultdict(int)
            for metrics in data['exec']:
                for region, cycles in metrics.region_cycles.items():
                    region_totals[region] += cycles

            if not region_totals:
                continue

            # Create pie chart with larger figure for better spacing
            fig, ax = plt.subplots(figsize=(14, 10))

            # Sort by cycles for better visualization
            sorted_regions = sorted(region_totals.items(), key=lambda x: x[1], reverse=True)
            labels = [self._format_region_name(r[0]) for r in sorted_regions]
            sizes = [r[1] for r in sorted_regions]

            # Calculate percentages for threshold
            total = sum(sizes)
            percentages = [(s / total) * 100 for s in sizes]

            # Use a color palette
            colors = plt.cm.Set3(np.linspace(0, 1, len(labels)))

            # Create labels only for slices > 2%, otherwise use legend
            display_labels = []
            for i, (label, pct) in enumerate(zip(labels, percentages)):
                if pct > 2.0:
                    display_labels.append(label)
                else:
                    display_labels.append('')  # Empty label for small slices

            # Explode small slices slightly for better visibility
            explode = [0.05 if pct < 5.0 else 0 for pct in percentages]

            # Create pie chart with percentages
            wedges, texts, autotexts = ax.pie(
                sizes,
                labels=display_labels,
                autopct=lambda pct: f'{pct:.1f}%' if pct > 2.0 else '',
                colors=colors,
                startangle=90,
                pctdistance=0.85,
                labeldistance=1.1,
                explode=explode
            )

            # Enhance text for labels
            for text in texts:
                text.set_fontsize(10)
                text.set_fontweight('bold')

            # Enhance text for percentages
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')
                autotext.set_fontsize(10)

            # Add a legend for all slices (especially helpful for small ones)
            legend_labels = [f'{label}: {pct:.1f}%' for label, pct in zip(labels, percentages)]
            ax.legend(
                legend_labels,
                loc='center left',
                bbox_to_anchor=(1, 0, 0.5, 1),
                fontsize=9
            )

            ax.set_title(f'SP1 - {data["label"]} Region Cycles Breakdown ({variant})',
                        fontsize=14, fontweight='bold', pad=20)

            plt.tight_layout()

            filename = f"region_cycles_{guest_type.replace('zkevm-metrics-bench-', '').replace('-', '_')}.png"
            output_path = output_dir / filename
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            plt.close()
            print(f"Saved: {output_path}")

    def plot_proving_time_ratio(self, all_data: Dict, output_path: Path, zkvm: str):
        """Create visualization showing ratio between execution-only and pre/post-state"""
        # Find the two guest types using the normalized keys
        exec_only_key = "execution_only"
        pre_post_key = "pre_post_state"

        if exec_only_key not in all_data or pre_post_key not in all_data:
            print(f"Warning: Missing data for ratio calculation")
            return

        exec_only_times = [m.proving_time_ms for m in all_data[exec_only_key]['prov']]
        pre_post_times = [m.proving_time_ms for m in all_data[pre_post_key]['prov']]

        if not exec_only_times or not pre_post_times:
            print(f"Warning: No proving data for ratio calculation")
            return

        avg_exec_only = np.mean(exec_only_times)
        avg_pre_post = np.mean(pre_post_times)

        ratio = avg_pre_post / avg_exec_only

        fig, ax = plt.subplots(figsize=(10, 6))

        bars = ax.bar(['Execution-Only', 'Pre/Post-State'],
                     [avg_exec_only, avg_pre_post],
                     color=['#2ecc71', '#e74c3c'], alpha=0.8)

        ax.set_ylabel('Average Proving Time (ms)', fontsize=12, fontweight='bold')
        ax.set_title(f'{zkvm.upper()} - Proving Time Comparison\nPre/Post-State is {ratio:.2f}x of Execution-Only',
                    fontsize=14, fontweight='bold')

        # Add value labels
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{height/1000:.1f}s',
                   ha='center', va='bottom', fontweight='bold', fontsize=12)

        # Add ratio annotation - position it between the bars to avoid overlap
        max_height = max(avg_exec_only, avg_pre_post)
        annotation_y = max_height * 0.85  # Place at 85% of max height
        ax.annotate(f'{ratio:.2f}x',
                   xy=(1, avg_pre_post), xytext=(0.5, annotation_y),
                   arrowprops=dict(arrowstyle='->', lw=2, color='red'),
                   fontsize=14, fontweight='bold', color='red',
                   ha='center')

        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"Saved: {output_path}")

    def plot_time_per_cycle(self, all_data: Dict, output_path: Path, zkvm: str):
        """Create bar chart for proving time per cycle metric"""
        fig, ax = plt.subplots(figsize=(10, 6))

        labels = []
        avg_time_per_cycle = []
        std_time_per_cycle = []

        for guest_type, data in all_data.items():
            combined = self.combine_metrics(data['exec'], data['prov'])

            if not combined:
                continue

            times_per_cycle = [m.proving_time_per_cycle for m in combined]
            labels.append(data['label'])
            avg_time_per_cycle.append(np.mean(times_per_cycle))
            std_time_per_cycle.append(np.std(times_per_cycle))

        x = np.arange(len(labels))
        bars = ax.bar(x, avg_time_per_cycle, yerr=std_time_per_cycle, capsize=5,
                     color=['#16a085', '#d35400'][:len(labels)], alpha=0.8)

        ax.set_xlabel('Guest Program Type', fontsize=12, fontweight='bold')
        ax.set_ylabel('Proving Time per Million Cycles (ms)', fontsize=12, fontweight='bold')
        ax.set_title(f'{zkvm.upper()} - Proving Time per Million Cycles',
                    fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(labels)

        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{height:.2f}',
                   ha='center', va='bottom', fontweight='bold')

        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"Saved: {output_path}")

    def generate_markdown_table(self, all_data: Dict, output_path: Path,
                               zkvm: str, include_time_per_cycle: bool):
        """Generate markdown table with raw statistics"""
        with open(output_path, 'w') as f:
            f.write(f"# {zkvm.upper()} - Benchmark Statistics\n\n")

            # Create table header
            if include_time_per_cycle:
                f.write("| Guest Program | Avg Proving Time (ms) | Avg Total Cycles | Avg Proving Time/Cycle (ms/M cycles) |\n")
                f.write("|---------------|----------------------|------------------|-------------------------------------|\n")
            else:
                f.write("| Guest Program | Avg Proving Time (ms) | Avg Total Cycles |\n")
                f.write("|---------------|----------------------|------------------|\n")

            # Add rows for each guest program
            for guest_type, data in all_data.items():
                label = data['label']

                # Calculate averages
                if data['prov']:
                    avg_proving_time = np.mean([m.proving_time_ms for m in data['prov']])
                else:
                    avg_proving_time = 0

                if data['exec']:
                    avg_cycles = np.mean([m.total_num_cycles for m in data['exec']])
                else:
                    avg_cycles = 0

                if include_time_per_cycle:
                    combined = self.combine_metrics(data['exec'], data['prov'])
                    if combined:
                        avg_time_per_cycle = np.mean([m.proving_time_per_cycle for m in combined])
                        f.write(f"| {label} | {avg_proving_time:,.0f} | {avg_cycles:,.0f} | {avg_time_per_cycle:.2f} |\n")
                    else:
                        f.write(f"| {label} | {avg_proving_time:,.0f} | {avg_cycles:,.0f} | N/A |\n")
                else:
                    f.write(f"| {label} | {avg_proving_time:,.0f} | {avg_cycles:,.0f} |\n")

            f.write("\n")

            # Add detailed statistics
            f.write("## Detailed Statistics\n\n")

            for guest_type, data in all_data.items():
                f.write(f"### {data['label']}\n\n")

                if data['prov']:
                    proving_times = [m.proving_time_ms for m in data['prov']]
                    f.write(f"**Proving Time:**\n")
                    f.write(f"- Min: {np.min(proving_times):,.0f} ms\n")
                    f.write(f"- Max: {np.max(proving_times):,.0f} ms\n")
                    f.write(f"- Avg: {np.mean(proving_times):,.0f} ms\n")
                    f.write(f"- Std Dev: {np.std(proving_times):,.0f} ms\n")
                    f.write(f"- Sample Size: {len(proving_times)} blocks\n\n")

                if data['exec']:
                    cycles = [m.total_num_cycles for m in data['exec']]
                    f.write(f"**Total Cycles:**\n")
                    f.write(f"- Min: {np.min(cycles):,.0f}\n")
                    f.write(f"- Max: {np.max(cycles):,.0f}\n")
                    f.write(f"- Avg: {np.mean(cycles):,.0f}\n")
                    f.write(f"- Std Dev: {np.std(cycles):,.0f}\n")
                    f.write(f"- Sample Size: {len(cycles)} blocks\n\n")

                if include_time_per_cycle:
                    combined = self.combine_metrics(data['exec'], data['prov'])
                    if combined:
                        time_per_cycle = [m.proving_time_per_cycle for m in combined]
                        f.write(f"**Proving Time per Million Cycles:**\n")
                        f.write(f"- Min: {np.min(time_per_cycle):.2f} ms\n")
                        f.write(f"- Max: {np.max(time_per_cycle):.2f} ms\n")
                        f.write(f"- Avg: {np.mean(time_per_cycle):.2f} ms\n")
                        f.write(f"- Std Dev: {np.std(time_per_cycle):.2f} ms\n")
                        f.write(f"- Sample Size: {len(combined)} blocks\n\n")

        print(f"Saved: {output_path}")

    def _format_region_name(self, region: str) -> str:
        """Format region name for better readability"""
        # Replace underscores with spaces and capitalize
        formatted = region.replace('_', ' ').title()
        # Shorten common prefixes
        formatted = formatted.replace('Public Inputs Preparation ', 'PI Prep: ')
        return formatted

    def create_comparison_charts(self, output_dir: Path):
        """Create comparison charts between with-checks and without-checks"""
        print("\n=== Creating Comparison Charts ===")

        comparison_dir = output_dir / "comparison"
        comparison_dir.mkdir(exist_ok=True)

        for zkvm in ["sp1-v5.2.1", "zisk-v0.13.0"]:
            zkvm_short = zkvm.split('-')[0]
            print(f"\n--- Creating comparison for {zkvm_short.upper()} ---")

            # Load data from both variants
            with_checks_base = self.base_path / "zkevm-metrics-benchs-with-checks"
            without_checks_base = self.base_path / "zkevm-metrics-benchs-without-checks"

            # Get execution-only data from both
            with_checks_exec = self.load_proving_data(
                with_checks_base / "proving" / "zkevm-metrics-bench-execution-only",
                "execution-only", zkvm
            )
            without_checks_exec = self.load_proving_data(
                without_checks_base / "proving" / "zkevm-metrics-bench-execution-only",
                "execution-only", zkvm
            )

            # Get pre-post-state data from both
            with_checks_prepost = self.load_proving_data(
                with_checks_base / "proving" / "zkevm-metrics-bench-pre-post-state-check",
                "pre-post-state", zkvm
            )
            without_checks_prepost = self.load_proving_data(
                without_checks_base / "proving" / "zkevm-metrics-bench-pre-post-state-check",
                "pre-post-state", zkvm
            )

            if not with_checks_exec or not without_checks_exec or not with_checks_prepost or not without_checks_prepost:
                print(f"Warning: Missing data for {zkvm_short} comparison")
                continue

            # Create comparison chart
            fig, ax = plt.subplots(figsize=(12, 7))

            labels = ['Execution-Only', 'Pre/Post-State']
            x = np.arange(len(labels))
            width = 0.35

            # Calculate averages
            with_checks_avgs = [
                np.mean([m.proving_time_ms for m in with_checks_exec]),
                np.mean([m.proving_time_ms for m in with_checks_prepost])
            ]
            without_checks_avgs = [
                np.mean([m.proving_time_ms for m in without_checks_exec]),
                np.mean([m.proving_time_ms for m in without_checks_prepost])
            ]

            # Create bars
            bars1 = ax.bar(x - width/2, with_checks_avgs, width, label='With Checks',
                          color='#e74c3c', alpha=0.8)
            bars2 = ax.bar(x + width/2, without_checks_avgs, width, label='Without Checks',
                          color='#2ecc71', alpha=0.8)

            ax.set_xlabel('Guest Program Type', fontsize=12, fontweight='bold')
            ax.set_ylabel('Average Proving Time (ms)', fontsize=12, fontweight='bold')
            ax.set_title(f'{zkvm_short.upper()} - With-Checks vs Without-Checks Overhead',
                        fontsize=14, fontweight='bold')
            ax.set_xticks(x)
            ax.set_xticklabels(labels)
            ax.legend(fontsize=11)

            # Add value labels and overhead percentages
            for i, (bar1, bar2) in enumerate(zip(bars1, bars2)):
                height1 = bar1.get_height()
                height2 = bar2.get_height()

                # Value labels
                ax.text(bar1.get_x() + bar1.get_width()/2., height1,
                       f'{height1/1000:.1f}s',
                       ha='center', va='bottom', fontweight='bold')
                ax.text(bar2.get_x() + bar2.get_width()/2., height2,
                       f'{height2/1000:.1f}s',
                       ha='center', va='bottom', fontweight='bold')

                # Overhead percentage
                overhead = ((height1 - height2) / height2) * 100
                ax.text(x[i], max(height1, height2) * 1.05,
                       f'+{overhead:.1f}%',
                       ha='center', va='bottom', fontweight='bold',
                       fontsize=11, color='red')

            plt.tight_layout()
            output_path = comparison_dir / f"{zkvm_short}_with_vs_without_checks.png"
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            plt.close()
            print(f"Saved: {output_path}")

            # Create markdown summary
            md_path = comparison_dir / f"{zkvm_short}_comparison_summary.md"
            with open(md_path, 'w') as f:
                f.write(f"# {zkvm_short.upper()} - With-Checks vs Without-Checks Comparison\n\n")

                f.write("## Execution-Only\n\n")
                exec_with = np.mean([m.proving_time_ms for m in with_checks_exec])
                exec_without = np.mean([m.proving_time_ms for m in without_checks_exec])
                exec_overhead = ((exec_with - exec_without) / exec_without) * 100
                f.write(f"- **With Checks:** {exec_with:,.0f} ms\n")
                f.write(f"- **Without Checks:** {exec_without:,.0f} ms\n")
                f.write(f"- **Overhead:** +{exec_overhead:.1f}%\n\n")

                f.write("## Pre/Post-State\n\n")
                prepost_with = np.mean([m.proving_time_ms for m in with_checks_prepost])
                prepost_without = np.mean([m.proving_time_ms for m in without_checks_prepost])
                prepost_overhead = ((prepost_with - prepost_without) / prepost_without) * 100
                f.write(f"- **With Checks:** {prepost_with:,.0f} ms\n")
                f.write(f"- **Without Checks:** {prepost_without:,.0f} ms\n")
                f.write(f"- **Overhead:** +{prepost_overhead:.1f}%\n\n")

            print(f"Saved: {md_path}")


def main():
    """Main entry point"""
    # Determine base path (script is in scripts/, data is in parent dir)
    script_dir = Path(__file__).parent
    base_path = script_dir.parent

    # Create output directory
    output_dir = base_path / "analysis_results"
    output_dir.mkdir(exist_ok=True)

    print("=" * 60)
    print("zkVM Proving Results Analysis")
    print("=" * 60)

    # Check if required folders exist
    with_checks = base_path / "zkevm-metrics-benchs-with-checks"
    without_checks = base_path / "zkevm-metrics-benchs-without-checks"

    if not with_checks.exists():
        print(f"Error: {with_checks} does not exist")
        sys.exit(1)

    if not without_checks.exists():
        print(f"Error: {without_checks} does not exist")
        sys.exit(1)

    # Create analyzer
    analyzer = ZKVMAnalyzer(base_path)

    # Run analyses
    analyzer.analyze_with_checks(output_dir)
    analyzer.analyze_without_checks(output_dir)

    # Create comparison charts
    analyzer.create_comparison_charts(output_dir)

    print("\n" + "=" * 60)
    print("Analysis complete!")
    print(f"Results saved to: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
