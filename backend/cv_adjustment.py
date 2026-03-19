"""
CV NPS Adjustment Tool

This module handles the matching of Transaction Reports and Feedback Reports,
auto-detection of non-server-related issues, and NPS recalculation.
"""

import pandas as pd
import re
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import logging

# Keywords that suggest the issue is NOT the server's fault
NON_SERVER_KEYWORDS = {
    # Food/Kitchen issues
    'food': ['dry', 'cold', 'overcooked', 'undercooked', 'raw', 'burnt', 'greasy', 'oily', 
             'salty', 'bland', 'tasteless', 'stale', 'portion', 'small portion', 'wrong order',
             'missing item', 'took forever', 'long wait for food', 'kitchen'],
    
    # Environment issues  
    'environment': ['cold', 'hot', 'loud', 'noisy', 'dirty', 'unclean', 'smell', 'air conditioning',
                   'ac', 'hvac', 'temperature', 'uncomfortable', 'crowded', 'windy'],
    
    # Host/Seating issues (not server)
    'host': ['hostess', 'host', 'seating', 'wait for table', 'reservation', 'no table'],
    
    # Management/Policy issues
    'management': ['policy', 'manager', 'management', 'price', 'expensive', 'overpriced'],
    
    # Other staff (not the server)
    'other_staff': ['busser', 'bartender made', 'kitchen staff', 'cook'],
}

# Keywords that indicate it IS the server's fault (override non-server detection)
SERVER_KEYWORDS = [
    'server', 'waiter', 'waitress', 'our server', 'the server', 'my server',
    'attentive', 'rude', 'ignored', 'slow service', 'never came back',
    'forgot', 'wrong order', 'attitude', 'dismissive'
]


def detect_non_server_issues(comment: str) -> Tuple[bool, List[str], str]:
    """
    Analyze a comment to detect if the issue is likely NOT the server's fault.
    
    Returns:
        (is_non_server, reasons, category)
    """
    if not comment or pd.isna(comment):
        return False, [], 'unknown'
    
    comment_lower = comment.lower()
    reasons = []
    categories_found = []
    
    # Check for non-server keywords
    for category, keywords in NON_SERVER_KEYWORDS.items():
        for keyword in keywords:
            if keyword in comment_lower:
                # Check if it's in context of praising the server but criticizing something else
                reasons.append(f"{category}: '{keyword}'")
                categories_found.append(category)
    
    # Check if server is specifically mentioned as the problem
    server_blamed = False
    for keyword in SERVER_KEYWORDS:
        if keyword in comment_lower:
            # Check context - is server being praised or blamed?
            # Look for negative words near server mentions
            negative_patterns = [
                r'server.{0,20}(horrible|terrible|bad|worst|rude|slow|ignored|never|forgot|dismissive)',
                r'(horrible|terrible|bad|worst|rude|slow).{0,20}server',
                r'waiter.{0,20}(horrible|terrible|bad|worst|rude|slow|ignored|never|forgot)',
                r'waitress.{0,20}(horrible|terrible|bad|worst|rude|slow|ignored|never|forgot)',
            ]
            for pattern in negative_patterns:
                if re.search(pattern, comment_lower):
                    server_blamed = True
                    break
    
    # If server is specifically blamed, it's a server issue regardless of other keywords
    if server_blamed:
        return False, ['Server specifically mentioned as the problem'], 'server'
    
    # If we found non-server issues but server was praised, likely not server's fault
    server_praised_patterns = [
        r'server was (great|amazing|excellent|wonderful|good|fantastic|awesome)',
        r'waiter was (great|amazing|excellent|wonderful|good|fantastic|awesome)',
        r'waitress was (great|amazing|excellent|wonderful|good|fantastic|awesome)',
        r'service was (great|amazing|excellent|wonderful|good|fantastic|awesome)',
    ]
    
    server_praised = any(re.search(p, comment_lower) for p in server_praised_patterns)
    
    if reasons and server_praised:
        return True, reasons + ['Server was praised'], categories_found[0] if categories_found else 'food'
    
    if reasons and not server_blamed:
        # Has non-server issues and server not blamed
        return True, reasons, categories_found[0] if categories_found else 'food'
    
    return False, [], 'unknown'


def parse_feedback_report(df: pd.DataFrame) -> List[Dict]:
    """
    Parse the Feedback Report into a structured list of feedback items.
    """
    feedback_items = []
    
    for _, row in df.iterrows():
        rating = int(row.get('Rating', 0))
        
        # Determine category (promoter/passive/detractor)
        if rating >= 9:
            nps_category = 'promoter'
        elif rating >= 7:
            nps_category = 'passive'
        else:
            nps_category = 'detractor'
        
        # The comment is in 'Check Category' column based on the data structure
        comment = row.get('Check Category', '')
        if pd.isna(comment):
            comment = ''
        
        # Auto-detect if this is likely not server's fault
        is_non_server, reasons, issue_category = detect_non_server_issues(str(comment))
        
        feedback_items.append({
            'id': str(row.get('Id', '')),
            'customer_name': row.get('Customer Name', ''),
            'check_number': str(row.get('Check Number', '')),
            'rating': rating,
            'nps_category': nps_category,
            'response_date': str(row.get('Response Date', '')),
            'date_of_business': str(row.get('Date Of Business', '')),
            'shift': row.get('Shift', ''),
            'revenue_center': row.get('Revenue Center', ''),
            'comment': str(comment) if comment else '',
            'lsc_account': str(row.get('LSC Account Number', '')),
            'store_name': row.get('Store Name', ''),
            'store_id': row.get('Store Id', ''),
            # Auto-detection fields
            'auto_flagged_non_server': is_non_server,
            'auto_flag_reasons': reasons,
            'issue_category': issue_category,
            # User can override
            'excluded': False,
            'exclusion_reason': '',
            'server_name': None,  # Will be matched from transaction report
        })
    
    return feedback_items


def parse_transaction_report(df: pd.DataFrame) -> Dict[str, Dict]:
    """
    Parse the Transaction Report into a lookup dictionary by check number.
    """
    transactions = {}
    
    for _, row in df.iterrows():
        check_num = str(row.get('CheckNumber', ''))
        transactions[check_num] = {
            'customer_name': row.get('CustomerName', ''),
            'account_number': str(row.get('AccountNumber', '')),
            'check_total': row.get('CheckTotal', 0),
            'store_name': row.get('StoreName', ''),
            'response_date': str(row.get('Response Date', '')),
            'shift': row.get('Shift', ''),
        }
    
    return transactions


def match_feedback_to_transactions(feedback_items: List[Dict], transactions: Dict[str, Dict]) -> List[Dict]:
    """
    Match feedback items to transactions using check number.
    Note: Transaction report doesn't have server name, but we keep this for future enhancement.
    """
    for item in feedback_items:
        check_num = item['check_number']
        if check_num in transactions:
            trans = transactions[check_num]
            # Currently transaction report doesn't have server name
            # This can be enhanced if server info becomes available
            item['transaction_matched'] = True
            item['check_total'] = trans.get('check_total', 0)
        else:
            item['transaction_matched'] = False
    
    return feedback_items


def calculate_nps(feedback_items: List[Dict], exclude_flagged: bool = False) -> Dict:
    """
    Calculate NPS score from feedback items.
    
    NPS = ((# Promoters) - (# Detractors)) / (# Responses) * 100
    
    Args:
        feedback_items: List of feedback items
        exclude_flagged: If True, exclude items marked as non-server issues
    
    Returns:
        Dict with NPS calculation details
    """
    items_to_count = feedback_items
    
    if exclude_flagged:
        items_to_count = [item for item in feedback_items if not item.get('excluded', False)]
    
    promoters = len([i for i in items_to_count if i['nps_category'] == 'promoter'])
    passives = len([i for i in items_to_count if i['nps_category'] == 'passive'])
    detractors = len([i for i in items_to_count if i['nps_category'] == 'detractor'])
    
    total_responses = promoters + passives + detractors
    
    if total_responses == 0:
        nps_score = 0
    else:
        nps_score = ((promoters - detractors) / total_responses) * 100
    
    return {
        'nps_score': round(nps_score, 2),
        'promoters': promoters,
        'passives': passives,
        'detractors': detractors,
        'total_responses': total_responses,
        'promoter_pct': round((promoters / total_responses * 100) if total_responses else 0, 1),
        'passive_pct': round((passives / total_responses * 100) if total_responses else 0, 1),
        'detractor_pct': round((detractors / total_responses * 100) if total_responses else 0, 1),
    }


def process_cv_reports(feedback_df: pd.DataFrame, transaction_df: pd.DataFrame = None) -> Dict:
    """
    Main function to process CV reports and calculate adjusted NPS.
    
    Returns:
        Dict with original NPS, adjusted NPS, and all feedback items for review
    """
    # Parse feedback
    feedback_items = parse_feedback_report(feedback_df)
    
    # Match to transactions if provided
    if transaction_df is not None:
        transactions = parse_transaction_report(transaction_df)
        feedback_items = match_feedback_to_transactions(feedback_items, transactions)
    
    # Calculate original NPS (all items)
    original_nps = calculate_nps(feedback_items, exclude_flagged=False)
    
    # Auto-apply exclusions for items flagged as non-server issues
    # Only for passives and detractors
    for item in feedback_items:
        if item['auto_flagged_non_server'] and item['nps_category'] in ['passive', 'detractor']:
            item['excluded'] = True
            item['exclusion_reason'] = 'auto: ' + ', '.join(item['auto_flag_reasons'])
    
    # Calculate adjusted NPS (excluding flagged items)
    adjusted_nps = calculate_nps(feedback_items, exclude_flagged=True)
    
    # Get counts for excluded items
    excluded_passives = len([i for i in feedback_items if i['excluded'] and i['nps_category'] == 'passive'])
    excluded_detractors = len([i for i in feedback_items if i['excluded'] and i['nps_category'] == 'detractor'])
    
    return {
        'original_nps': original_nps,
        'adjusted_nps': adjusted_nps,
        'feedback_items': feedback_items,
        'excluded_count': {
            'passives': excluded_passives,
            'detractors': excluded_detractors,
            'total': excluded_passives + excluded_detractors,
        },
        'summary': {
            'total_feedback': len(feedback_items),
            'promoters': original_nps['promoters'],
            'passives': original_nps['passives'],
            'detractors': original_nps['detractors'],
            'auto_flagged': len([i for i in feedback_items if i['auto_flagged_non_server']]),
        }
    }


# Test the module
if __name__ == "__main__":
    # Test with sample comments
    test_comments = [
        "The server was amazing. The boil was a bit too oily and overcooked.",
        "We had a older lady who was a horrible server, made excuses about not getting what we ordered.",
        "Food was very greasy and I didn't enjoy my meal. Service was very good.",
        "Our waitress was awesome, very attentive. The salmon was overcooked and so dry.",
        "Server ignored us the whole time.",
    ]
    
    print("=== Testing Non-Server Detection ===")
    for comment in test_comments:
        is_non_server, reasons, category = detect_non_server_issues(comment)
        print(f"\nComment: {comment[:80]}...")
        print(f"Non-server issue: {is_non_server}")
        print(f"Reasons: {reasons}")
        print(f"Category: {category}")
