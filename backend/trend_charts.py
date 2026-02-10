"""
Trend Chart Generator
Generates comparison charts showing employee/team performance across quarters.
"""
import io
import base64
from typing import List, Dict, Any, Optional, Tuple
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# Chart styling constants
COLORS = {
    'primary': '#D12E2E',      # Bubba Gump Red
    'secondary': '#005B96',    # Corporate Blue
    'previous': '#9CA3AF',     # Gray for previous quarter
    'current': '#D12E2E',      # Red for current quarter
    'background': '#FFFFFF',
    'grid': '#E5E7EB',
    'text': '#374151',
    'positive': '#16A34A',     # Green for improvement
    'negative': '#DC2626',     # Red for decline
}

# Metric definitions
METRICS_CONFIG = {
    'ppa': {'label': 'PPA', 'format': '${:.2f}', 'benchmark': 55.0, 'higher_better': True},
    'lbw_per_guest': {'label': 'LBW/Guest', 'format': '${:.2f}', 'benchmark': 8.0, 'higher_better': True},
    'glassware_per_guest': {'label': 'Glass/Guest', 'format': '${:.2f}', 'benchmark': 1.0, 'higher_better': True},
    'guests_per_lsc': {'label': 'Guests/LSC', 'format': '{:.1f}', 'benchmark': 100.0, 'higher_better': False},
    'cv_score': {'label': 'CV Score', 'format': '{:.1f}', 'benchmark': 5.0, 'higher_better': True},
    'pre_dar_score': {'label': 'Total Score', 'format': '{:.1f}', 'benchmark': 85.0, 'higher_better': True},
}


def get_previous_quarter(quarter: str, year: int) -> Tuple[str, int]:
    """Get the previous quarter and year."""
    quarters = ['Q1', 'Q2', 'Q3', 'Q4']
    q_index = quarters.index(quarter.upper())
    
    if q_index == 0:
        return 'Q4', year - 1
    else:
        return quarters[q_index - 1], year


def generate_employee_comparison_chart(
    employee_name: str,
    current_data: Dict[str, Any],
    previous_data: Optional[Dict[str, Any]],
    current_quarter: str,
    current_year: int,
    metrics: List[str] = None,
    benchmarks: Dict[str, float] = None,
    restaurant_averages: Dict[str, float] = None,
    snapshot_history: List[Dict[str, Any]] = None,
    restaurant_avg_history: List[Dict[str, Any]] = None
) -> bytes:
    """
    Generate a multi-panel chart with one graph per metric.
    Each graph shows:
    - Solid line: Employee's value over time
    - Dashed horizontal line: Benchmark (flat)
    - Dotted line: Restaurant average over time
    
    Returns PNG image bytes.
    """
    if metrics is None:
        metrics = ['ppa', 'lbw_per_guest', 'glassware_per_guest', 'guests_per_lsc', 'cv_score', 'pre_dar_score']
    
    # Default benchmarks
    if benchmarks is None:
        benchmarks = {m: METRICS_CONFIG.get(m, {}).get('benchmark', 0) for m in metrics}
    
    # Setup figure with 2 rows x 3 columns
    fig, axes = plt.subplots(2, 3, figsize=(16, 10), facecolor=COLORS['background'])
    axes = axes.flatten()
    
    # Get snapshot dates
    if snapshot_history and len(snapshot_history) > 0:
        dates = sorted(set(s.get('date', '') for s in snapshot_history))
    else:
        # Fallback to current/previous quarter
        prev_quarter, prev_year = get_previous_quarter(current_quarter, current_year)
        dates = [f'{prev_quarter} {prev_year}', f'{current_quarter} {current_year}']
    
    # Format date labels
    date_labels = []
    for d in dates:
        try:
            from datetime import datetime as dt
            parsed = dt.strptime(d, "%Y-%m-%d")
            date_labels.append(parsed.strftime("%b %d"))
        except:
            date_labels.append(d[-5:] if len(d) >= 5 else d)
    
    x = np.arange(len(dates))
    
    for idx, metric in enumerate(metrics):
        ax = axes[idx]
        ax.set_facecolor('#FAFAFA')  # Slight off-white for contrast
        
        config = METRICS_CONFIG.get(metric, {'label': metric, 'format': '{:.1f}', 'benchmark': 0})
        metric_label = config['label']
        benchmark_val = benchmarks.get(metric, config.get('benchmark', 0)) or 0
        
        # Get employee values for this metric from snapshots
        emp_values = []
        rest_values = []
        plot_dates = []
        plot_date_labels = []
        
        if snapshot_history and len(snapshot_history) > 0:
            # Build lookup from snapshot history
            snap_by_date = {}
            for snap in snapshot_history:
                snap_date = snap.get('date', '')
                snap_by_date[snap_date] = snap
            
            rest_by_date = {}
            if restaurant_avg_history:
                for r in restaurant_avg_history:
                    rest_by_date[r.get('date', '')] = r
            
            # Only include dates where this employee has valid data for this metric
            for i, d in enumerate(dates):
                snap = snap_by_date.get(d, {})
                emp_val = snap.get(metric, None)
                
                # Skip if employee has no data or zero value for this metric on this date
                if emp_val is None or emp_val == 0:
                    continue
                
                emp_values.append(emp_val)
                plot_dates.append(i)
                plot_date_labels.append(date_labels[i] if i < len(date_labels) else d)
                
                rest_snap = rest_by_date.get(d, {})
                rest_val = rest_snap.get(metric, 0) or 0
                rest_values.append(rest_val)
        else:
            # Fallback to current/previous data
            plot_dates = list(range(len(dates)))
            plot_date_labels = date_labels
            if previous_data:
                emp_values.append(previous_data.get(metric, 0) or 0)
                rest_values.append(restaurant_averages.get(metric, 0) * 0.95 if restaurant_averages else 0)
            emp_values.append(current_data.get(metric, 0) or 0)
            rest_values.append(restaurant_averages.get(metric, 0) if restaurant_averages else 0)
        
        # Skip this metric if no valid data points
        if not emp_values:
            ax.text(0.5, 0.5, 'No data', ha='center', va='center', fontsize=10, 
                   color=COLORS['text'], transform=ax.transAxes)
            ax.set_title(metric_label, fontsize=12, fontweight='bold', color=COLORS['text'], pad=10)
            continue
        
        x = np.arange(len(emp_values))
        
        # Plot employee line - solid red
        ax.plot(x, emp_values, 'o-', color=COLORS['primary'], linewidth=2.5, markersize=8,
                label=employee_name, zorder=3)
        
        # Plot restaurant average - dotted blue (only non-zero values)
        valid_rest = [(i, v) for i, v in enumerate(rest_values) if v > 0]
        if valid_rest:
            rest_x = [v[0] for v in valid_rest]
            rest_y = [v[1] for v in valid_rest]
            ax.plot(rest_x, rest_y, '^:', color=COLORS['secondary'], linewidth=2, markersize=6,
                    label='Restaurant Avg', alpha=0.85, zorder=2)
        
        # Plot benchmark as horizontal dashed line - green (FLAT)
        ax.axhline(y=benchmark_val, color=COLORS['positive'], linestyle='--', linewidth=2,
                   label=f'Benchmark ({config["format"].format(benchmark_val)})', alpha=0.85, zorder=1)
        
        # Add value labels for employee points
        for xi, val in zip(x, emp_values):
            if val > 0:
                formatted_val = config['format'].format(val)
                ax.annotate(formatted_val,
                           xy=(xi, val),
                           xytext=(0, 10), textcoords="offset points",
                           ha='center', va='bottom', fontsize=10, fontweight='bold',
                           color=COLORS['primary'],
                           bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8, edgecolor='none'))
        
        # Styling - Add box/border around each subplot
        ax.set_title(metric_label, fontsize=12, fontweight='bold', color=COLORS['text'], pad=10)
        ax.set_xticks(x)
        ax.set_xticklabels(plot_date_labels[:len(x)], fontsize=9, rotation=45 if len(x) > 4 else 0, 
                          ha='right' if len(x) > 4 else 'center')
        
        # Calculate y-axis range to fit ALL lines (employee, benchmark, restaurant avg)
        all_vals = list(emp_values)  # Always include employee values
        all_vals.extend([v for v in rest_values if v > 0])  # Include non-zero restaurant values
        all_vals.append(benchmark_val)  # Always include benchmark
        
        if all_vals:
            min_val = min(all_vals)
            max_val = max(all_vals)
            # Add 20% padding on both sides to ensure no line is cut off
            value_range = max_val - min_val if max_val != min_val else max_val * 0.5
            padding = value_range * 0.25
            y_min = max(0, min_val - padding)
            y_max = max_val + padding
            ax.set_ylim(y_min, y_max)
        
        # Grid
        ax.yaxis.grid(True, linestyle='--', alpha=0.5, color=COLORS['grid'])
        ax.set_axisbelow(True)
        
        # Add visible border/box around each graph
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_color('#CCCCCC')
            spine.set_linewidth(1.5)
        
        # Add a subtle shadow effect with a rectangle patch
        ax.patch.set_edgecolor('#AAAAAA')
        ax.patch.set_linewidth(2)
        
        # Legend only on first chart
        if idx == 0:
            ax.legend(loc='upper left', framealpha=0.95, fontsize=8, 
                     fancybox=True, shadow=True, borderpad=0.8)
    
    # Main title
    fig.suptitle(f'{employee_name} - {current_quarter} {current_year} Performance Trends', 
                fontsize=16, fontweight='bold', color=COLORS['primary'], y=0.98)
    
    plt.tight_layout(rect=[0, 0, 1, 0.95], h_pad=2.5, w_pad=2.0)
    
    # Save to bytes
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor=COLORS['background'])
    plt.close(fig)
    buffer.seek(0)
    
    return buffer.getvalue()


def _generate_time_series_chart(
    employee_name: str,
    snapshot_history: List[Dict[str, Any]],
    restaurant_avg_history: List[Dict[str, Any]],
    benchmark_score: float,
    current_quarter: str,
    current_year: int
) -> bytes:
    """
    Generate a time-series line chart from snapshot data.
    - Solid line: Employee's total score
    - Dashed horizontal line: Benchmark (flat)
    - Dotted line: Restaurant average
    """
    # Sort by date
    snapshot_history = sorted(snapshot_history, key=lambda x: x.get('date', ''))
    
    # Extract data
    dates = []
    emp_scores = []
    for snap in snapshot_history:
        dates.append(snap.get('date', ''))
        emp_scores.append(snap.get('total_score', snap.get('pre_dar_score', 0)) or 0)
    
    # Match restaurant averages to dates
    rest_avg_dict = {d.get('date', ''): d.get('avg_score', 0) for d in (restaurant_avg_history or [])}
    rest_scores = [rest_avg_dict.get(d, 0) for d in dates]
    
    # Format date labels
    date_labels = []
    for d in dates:
        try:
            from datetime import datetime as dt
            parsed = dt.strptime(d, "%Y-%m-%d")
            date_labels.append(parsed.strftime("%b %d"))
        except:
            date_labels.append(d[-5:] if len(d) >= 5 else d)
    
    # Setup figure
    fig, ax = plt.subplots(figsize=(12, 6), facecolor=COLORS['background'])
    ax.set_facecolor(COLORS['background'])
    
    x = np.arange(len(dates))
    
    # Plot employee line - solid red
    ax.plot(x, emp_scores, 'o-', color=COLORS['primary'], linewidth=3, markersize=10,
            label=employee_name, zorder=3)
    
    # Plot restaurant average line - dotted blue  
    valid_rest = [(i, s) for i, s in enumerate(rest_scores) if s > 0]
    if valid_rest:
        rest_x = [v[0] for v in valid_rest]
        rest_y = [v[1] for v in valid_rest]
        ax.plot(rest_x, rest_y, '^:', color=COLORS['secondary'], linewidth=2.5, markersize=8,
                label='Restaurant Avg', alpha=0.85, zorder=2)
    
    # Plot benchmark as horizontal dashed line - green (FLAT LINE)
    ax.axhline(y=benchmark_score, color=COLORS['positive'], linestyle='--', linewidth=2.5,
               label=f'Benchmark ({benchmark_score})', alpha=0.85, zorder=1)
    
    # Add value labels for employee points
    for xi, score in zip(x, emp_scores):
        ax.annotate(f'{score:.1f}',
                   xy=(xi, score),
                   xytext=(0, 12), textcoords="offset points",
                   ha='center', va='bottom', fontsize=10, fontweight='bold',
                   color=COLORS['primary'])
    
    # Styling
    ax.set_xlabel('Snapshot Date', fontsize=12, color=COLORS['text'])
    ax.set_ylabel('Total Score', fontsize=12, color=COLORS['text'])
    ax.set_title(f'{employee_name} - {current_quarter} {current_year} Performance Trend', 
                fontsize=14, fontweight='bold', color=COLORS['primary'], pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(date_labels, fontsize=10, rotation=45 if len(dates) > 5 else 0, ha='right' if len(dates) > 5 else 'center')
    ax.legend(loc='upper left', framealpha=0.95, fontsize=10)
    
    # Grid
    ax.yaxis.grid(True, linestyle='--', alpha=0.7, color=COLORS['grid'])
    ax.xaxis.grid(True, linestyle='--', alpha=0.3, color=COLORS['grid'])
    ax.set_axisbelow(True)
    
    # Set y-axis range
    all_vals = emp_scores + [s for s in rest_scores if s > 0] + [benchmark_score]
    min_val = max(0, min(all_vals) - 10)
    max_val = min(120, max(all_vals) + 10)
    ax.set_ylim(min_val, max_val)
    
    # Remove spines
    for spine in ['top', 'right']:
        ax.spines[spine].set_visible(False)
    ax.spines['left'].set_color(COLORS['grid'])
    ax.spines['bottom'].set_color(COLORS['grid'])
    
    plt.tight_layout()
    
    # Save to bytes
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor=COLORS['background'])
    plt.close(fig)
    buffer.seek(0)
    
    return buffer.getvalue()


def generate_employee_change_chart(
    employee_name: str,
    current_data: Dict[str, Any],
    previous_data: Optional[Dict[str, Any]],
    current_quarter: str,
    current_year: int,
    metrics: List[str] = None
) -> bytes:
    """
    Generate a horizontal bar chart showing % change for each metric.
    Green = improvement, Red = decline.
    
    Returns PNG image bytes.
    """
    if metrics is None:
        metrics = ['ppa', 'lbw_per_guest', 'glassware_per_guest', 'guests_per_lsc', 'cv_score', 'pre_dar_score']
    
    prev_quarter, prev_year = get_previous_quarter(current_quarter, current_year)
    
    # Calculate changes
    changes = []
    labels = []
    colors_list = []
    
    for metric in metrics:
        config = METRICS_CONFIG.get(metric, {'label': metric, 'higher_better': True})
        labels.append(config['label'])
        
        curr_val = current_data.get(metric, 0) or 0
        prev_val = previous_data.get(metric, 0) if previous_data else 0
        
        if prev_val and prev_val != 0:
            pct_change = ((curr_val - prev_val) / abs(prev_val)) * 100
        else:
            pct_change = 0 if curr_val == 0 else 100
        
        # Invert for guests_per_lsc (lower is better)
        if not config.get('higher_better', True):
            pct_change = -pct_change
        
        changes.append(pct_change)
        colors_list.append(COLORS['positive'] if pct_change >= 0 else COLORS['negative'])
    
    # Setup figure
    fig, ax = plt.subplots(figsize=(10, 5), facecolor=COLORS['background'])
    ax.set_facecolor(COLORS['background'])
    
    y = np.arange(len(metrics))
    
    # Create horizontal bars
    bars = ax.barh(y, changes, color=colors_list, edgecolor='white', linewidth=1, height=0.6)
    
    # Add value labels
    for bar, change in zip(bars, changes):
        width = bar.get_width()
        label_x = width + 2 if width >= 0 else width - 2
        ha = 'left' if width >= 0 else 'right'
        ax.annotate(f'{change:+.1f}%',
                   xy=(label_x, bar.get_y() + bar.get_height() / 2),
                   ha=ha, va='center', fontsize=10, fontweight='bold',
                   color=COLORS['text'])
    
    # Add zero line
    ax.axvline(x=0, color=COLORS['text'], linewidth=1, alpha=0.5)
    
    # Styling
    ax.set_xlabel('% Change (Positive = Improvement)', fontsize=11, color=COLORS['text'])
    ax.set_title(f'📈 {employee_name} - Performance Change ({prev_quarter} → {current_quarter})', 
                fontsize=14, fontweight='bold', color=COLORS['primary'], pad=15)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    
    # Grid
    ax.xaxis.grid(True, linestyle='--', alpha=0.7, color=COLORS['grid'])
    ax.set_axisbelow(True)
    
    # Remove spines
    for spine in ['top', 'right']:
        ax.spines[spine].set_visible(False)
    
    # Legend
    positive_patch = mpatches.Patch(color=COLORS['positive'], label='Improvement')
    negative_patch = mpatches.Patch(color=COLORS['negative'], label='Decline')
    ax.legend(handles=[positive_patch, negative_patch], loc='lower right', framealpha=0.9)
    
    plt.tight_layout()
    
    # Save to bytes
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor=COLORS['background'])
    plt.close(fig)
    buffer.seek(0)
    
    return buffer.getvalue()


def generate_team_comparison_chart(
    current_employees: List[Dict[str, Any]],
    previous_employees: List[Dict[str, Any]],
    current_quarter: str,
    current_year: int,
    metrics: List[str] = None
) -> bytes:
    """
    Generate a team-wide comparison chart showing average metrics.
    
    Returns PNG image bytes.
    """
    if metrics is None:
        metrics = ['ppa', 'lbw_per_guest', 'glassware_per_guest', 'cv_score', 'pre_dar_score']
    
    prev_quarter, prev_year = get_previous_quarter(current_quarter, current_year)
    
    # Calculate team averages
    def calc_avg(employees, metric):
        values = [e.get(metric, 0) for e in employees if e.get(metric) is not None]
        return sum(values) / len(values) if values else 0
    
    # Setup figure
    fig, ax = plt.subplots(figsize=(12, 6), facecolor=COLORS['background'])
    ax.set_facecolor(COLORS['background'])
    
    x = np.arange(len(metrics))
    width = 0.35
    
    current_avgs = []
    previous_avgs = []
    labels = []
    
    for metric in metrics:
        config = METRICS_CONFIG.get(metric, {'label': metric})
        labels.append(config['label'])
        
        curr_avg = calc_avg(current_employees, metric)
        prev_avg = calc_avg(previous_employees, metric) if previous_employees else 0
        
        # Normalize guests_per_lsc
        if metric == 'guests_per_lsc':
            curr_avg = curr_avg / 10
            prev_avg = prev_avg / 10
        
        current_avgs.append(curr_avg)
        previous_avgs.append(prev_avg)
    
    # Create bars
    ax.bar(x - width/2, previous_avgs, width, label=f'{prev_quarter} {prev_year} Team Avg', 
           color=COLORS['previous'], edgecolor='white', linewidth=1)
    bars2 = ax.bar(x + width/2, current_avgs, width, label=f'{current_quarter} {current_year} Team Avg', 
                   color=COLORS['secondary'], edgecolor='white', linewidth=1)
    
    # Add value labels
    for bar, val, metric in zip(bars2, current_avgs, metrics):
        height = bar.get_height()
        config = METRICS_CONFIG.get(metric, {'format': '{:.1f}'})
        display_val = val * 10 if metric == 'guests_per_lsc' else val
        formatted = config['format'].format(display_val)
        
        ax.annotate(formatted,
                   xy=(bar.get_x() + bar.get_width() / 2, height),
                   xytext=(0, 3), textcoords="offset points",
                   ha='center', va='bottom', fontsize=9, fontweight='bold',
                   color=COLORS['text'])
    
    # Styling
    ax.set_xlabel('Metrics', fontsize=11, color=COLORS['text'])
    ax.set_ylabel('Team Average', fontsize=11, color=COLORS['text'])
    ax.set_title(f'📊 Team Performance Comparison - {prev_quarter} vs {current_quarter} {current_year}', 
                fontsize=14, fontweight='bold', color=COLORS['secondary'], pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.legend(loc='upper right', framealpha=0.9)
    
    # Grid
    ax.yaxis.grid(True, linestyle='--', alpha=0.7, color=COLORS['grid'])
    ax.set_axisbelow(True)
    
    # Remove spines
    for spine in ['top', 'right']:
        ax.spines[spine].set_visible(False)
    
    plt.tight_layout()
    
    # Save to bytes
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor=COLORS['background'])
    plt.close(fig)
    buffer.seek(0)
    
    return buffer.getvalue()


def generate_tier_distribution_chart(
    current_employees: List[Dict[str, Any]],
    previous_employees: List[Dict[str, Any]],
    current_quarter: str,
    current_year: int
) -> bytes:
    """
    Generate a chart showing tier distribution comparison.
    
    Returns PNG image bytes.
    """
    prev_quarter, prev_year = get_previous_quarter(current_quarter, current_year)
    
    tiers = ['Trainer', 'Bartender', 'A-Server', 'B-Server', 'C-Server']
    tier_colors = ['#9333EA', '#2563EB', '#16A34A', '#CA8A04', '#DC2626']
    
    def count_tiers(employees):
        counts = {t: 0 for t in tiers}
        for emp in employees:
            tier = emp.get('tier_label', 'C-Server')
            if tier in counts:
                counts[tier] += 1
        return [counts[t] for t in tiers]
    
    current_counts = count_tiers(current_employees)
    previous_counts = count_tiers(previous_employees) if previous_employees else [0] * len(tiers)
    
    # Setup figure
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), facecolor=COLORS['background'])
    
    for ax, counts, title, quarter, year in [
        (axes[0], previous_counts, f'{prev_quarter} {prev_year}', prev_quarter, prev_year),
        (axes[1], current_counts, f'{current_quarter} {current_year}', current_quarter, current_year)
    ]:
        ax.set_facecolor(COLORS['background'])
        
        # Filter out zero values for pie chart
        non_zero_indices = [i for i, c in enumerate(counts) if c > 0]
        filtered_counts = [counts[i] for i in non_zero_indices]
        filtered_labels = [tiers[i] for i in non_zero_indices]
        filtered_colors = [tier_colors[i] for i in non_zero_indices]
        
        if filtered_counts:
            wedges, texts, autotexts = ax.pie(
                filtered_counts, labels=filtered_labels, colors=filtered_colors,
                autopct='%1.0f%%', startangle=90, pctdistance=0.75,
                textprops={'fontsize': 10}
            )
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')
        
        ax.set_title(title, fontsize=12, fontweight='bold', color=COLORS['text'])
    
    fig.suptitle('📈 Server Tier Distribution Comparison', fontsize=14, fontweight='bold', 
                color=COLORS['secondary'], y=1.02)
    
    plt.tight_layout()
    
    # Save to bytes
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor=COLORS['background'])
    plt.close(fig)
    buffer.seek(0)
    
    return buffer.getvalue()


def chart_to_base64(chart_bytes: bytes) -> str:
    """Convert chart bytes to base64 string."""
    return base64.b64encode(chart_bytes).decode('utf-8')


def generate_biweekly_trend_chart(
    employee_name: str,
    employee_scores: List[Dict[str, Any]],
    restaurant_averages: List[Dict[str, Any]],
    quarter: str = None,
    year: int = None,
    time_range: str = "quarter"  # "quarter", "year", or "all"
) -> bytes:
    """
    Generate a line chart showing employee Total Score vs Restaurant Average over bi-weekly snapshots.
    
    Args:
        employee_name: Name of the employee
        employee_scores: List of dicts with 'date' and 'total_score' for the employee
        restaurant_averages: List of dicts with 'date' and 'avg_score' for restaurant
        quarter: Current quarter (e.g., "Q1")
        year: Current year (e.g., 2026)
        time_range: "quarter" (default), "year", or "all"
    
    Returns PNG image bytes.
    """
    if not employee_scores:
        # Return empty chart if no data
        fig, ax = plt.subplots(figsize=(10, 5), facecolor=COLORS['background'])
        ax.text(0.5, 0.5, 'No snapshot data available', ha='center', va='center', 
                fontsize=14, color=COLORS['text'], transform=ax.transAxes)
        ax.set_facecolor(COLORS['background'])
        ax.axis('off')
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor=COLORS['background'])
        plt.close(fig)
        buffer.seek(0)
        return buffer.getvalue()
    
    # Sort by date
    employee_scores = sorted(employee_scores, key=lambda x: x['date'])
    restaurant_averages = sorted(restaurant_averages, key=lambda x: x['date'])
    
    # Extract data
    dates = [d['date'] for d in employee_scores]
    emp_scores = [d['total_score'] for d in employee_scores]
    
    # Match restaurant averages to employee dates
    rest_avg_dict = {d['date']: d['avg_score'] for d in restaurant_averages}
    rest_scores = [rest_avg_dict.get(d, None) for d in dates]
    
    # Format dates for display
    date_labels = []
    for d in dates:
        try:
            from datetime import datetime as dt
            parsed = dt.strptime(d, "%Y-%m-%d")
            date_labels.append(parsed.strftime("%b %d"))
        except:
            date_labels.append(d[-5:])  # Last 5 chars as fallback
    
    # Setup figure
    fig, ax = plt.subplots(figsize=(10, 5), facecolor=COLORS['background'])
    ax.set_facecolor(COLORS['background'])
    
    x = np.arange(len(dates))
    
    # Plot employee line (red, primary)
    ax.plot(x, emp_scores, 'o-', color=COLORS['primary'], linewidth=2.5, markersize=8,
            label=employee_name, zorder=3)
    
    # Plot restaurant average line (blue, secondary)
    # Filter out None values
    valid_rest_indices = [i for i, s in enumerate(rest_scores) if s is not None]
    if valid_rest_indices:
        rest_x = [x[i] for i in valid_rest_indices]
        rest_y = [rest_scores[i] for i in valid_rest_indices]
        ax.plot(rest_x, rest_y, 's--', color=COLORS['secondary'], linewidth=2, markersize=6,
                label='Restaurant Avg', alpha=0.8, zorder=2)
    
    # Add data point labels for employee
    for i, (xi, score) in enumerate(zip(x, emp_scores)):
        ax.annotate(f'{score:.1f}', (xi, score), textcoords="offset points",
                   xytext=(0, 10), ha='center', fontsize=9, fontweight='bold',
                   color=COLORS['primary'])
    
    # Add benchmark line at 80 (Meeting Expectations threshold)
    ax.axhline(y=80, color=COLORS['positive'], linestyle=':', linewidth=1.5, 
               alpha=0.7, label='Meeting Expectations (80)')
    
    # Styling
    ax.set_xlabel('Snapshot Date', fontsize=11, color=COLORS['text'])
    ax.set_ylabel('Total Score', fontsize=11, color=COLORS['text'])
    
    # Title based on time range
    if time_range == "quarter" and quarter and year:
        title = f'{employee_name} - {quarter} {year} Performance Trend'
    elif time_range == "year" and year:
        title = f'{employee_name} - {year} Performance Trend'
    else:
        title = f'{employee_name} - Performance Trend'
    
    ax.set_title(title, fontsize=14, fontweight='bold', color=COLORS['primary'], pad=15)
    
    ax.set_xticks(x)
    ax.set_xticklabels(date_labels, fontsize=10, rotation=45, ha='right')
    
    # Set y-axis range with some padding
    all_scores = emp_scores + [s for s in rest_scores if s is not None]
    if all_scores:
        min_score = max(0, min(all_scores) - 10)
        max_score = min(120, max(all_scores) + 10)
        ax.set_ylim(min_score, max_score)
    
    # Legend
    ax.legend(loc='upper left', framealpha=0.9, fontsize=9)
    
    # Grid
    ax.yaxis.grid(True, linestyle='--', alpha=0.7, color=COLORS['grid'])
    ax.xaxis.grid(True, linestyle='--', alpha=0.3, color=COLORS['grid'])
    ax.set_axisbelow(True)
    
    # Remove top and right spines
    for spine in ['top', 'right']:
        ax.spines[spine].set_visible(False)
    ax.spines['left'].set_color(COLORS['grid'])
    ax.spines['bottom'].set_color(COLORS['grid'])
    
    plt.tight_layout()
    
    # Save to bytes
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor=COLORS['background'])
    plt.close(fig)
    buffer.seek(0)
    
    return buffer.getvalue()
