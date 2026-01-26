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
    metrics: List[str] = None
) -> bytes:
    """
    Generate a comparison bar chart for an individual employee.
    Shows current vs previous quarter metrics.
    
    Returns PNG image bytes.
    """
    if metrics is None:
        metrics = ['ppa', 'lbw_per_guest', 'glassware_per_guest', 'guests_per_lsc', 'cv_score', 'pre_dar_score']
    
    prev_quarter, prev_year = get_previous_quarter(current_quarter, current_year)
    
    # Setup figure
    fig, ax = plt.subplots(figsize=(12, 6), facecolor=COLORS['background'])
    ax.set_facecolor(COLORS['background'])
    
    # Prepare data
    x = np.arange(len(metrics))
    width = 0.35
    
    current_values = []
    previous_values = []
    labels = []
    
    for metric in metrics:
        config = METRICS_CONFIG.get(metric, {'label': metric, 'format': '{:.1f}'})
        labels.append(config['label'])
        
        curr_val = current_data.get(metric, 0) or 0
        prev_val = previous_data.get(metric, 0) if previous_data else 0
        
        # Normalize for display (scale guests_per_lsc)
        if metric == 'guests_per_lsc':
            curr_val = curr_val / 10  # Scale down for chart
            prev_val = prev_val / 10 if prev_val else 0
        
        current_values.append(curr_val)
        previous_values.append(prev_val)
    
    # Create bars
    bars1 = ax.bar(x - width/2, previous_values, width, label=f'{prev_quarter} {prev_year}', 
                   color=COLORS['previous'], edgecolor='white', linewidth=1)
    bars2 = ax.bar(x + width/2, current_values, width, label=f'{current_quarter} {current_year}', 
                   color=COLORS['current'], edgecolor='white', linewidth=1)
    
    # Add value labels on bars
    for bar, val, metric in zip(bars2, current_values, metrics):
        height = bar.get_height()
        config = METRICS_CONFIG.get(metric, {'format': '{:.1f}'})
        
        # Undo scaling for display
        display_val = val * 10 if metric == 'guests_per_lsc' else val
        formatted = config['format'].format(display_val)
        
        ax.annotate(formatted,
                   xy=(bar.get_x() + bar.get_width() / 2, height),
                   xytext=(0, 3), textcoords="offset points",
                   ha='center', va='bottom', fontsize=9, fontweight='bold',
                   color=COLORS['text'])
    
    # Styling
    ax.set_xlabel('Metrics', fontsize=11, color=COLORS['text'])
    ax.set_ylabel('Value', fontsize=11, color=COLORS['text'])
    ax.set_title(f'📊 {employee_name} - Quarter Comparison', fontsize=14, fontweight='bold', 
                color=COLORS['primary'], pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.legend(loc='upper right', framealpha=0.9)
    
    # Grid
    ax.yaxis.grid(True, linestyle='--', alpha=0.7, color=COLORS['grid'])
    ax.set_axisbelow(True)
    
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
    bars1 = ax.bar(x - width/2, previous_avgs, width, label=f'{prev_quarter} {prev_year} Team Avg', 
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
