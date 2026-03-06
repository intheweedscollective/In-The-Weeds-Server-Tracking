"""
Smart Name Matcher for Employee CV Attribution
Handles nickname/legal name variations automatically.
"""

from typing import Dict, List, Optional, Tuple
from difflib import SequenceMatcher
import re

# Common nickname to legal name mappings
NICKNAME_MAP = {
    # First names
    "trey": ["treyanna", "tre"],
    "tad": ["thaddeus"],
    "tk": ["thomas", "t.k."],
    "abby": ["abigail"],
    "ikey": ["eric", "ike"],
    "keisha": ["lakeisha", "lakiesha", "kiesha"],
    "sheri": ["sheridan", "sherry"],
    "kelsey": ["keisey"],  # typo variant
    "keisey": ["kelsey"],
    "matt": ["matthew"],
    "mike": ["michael"],
    "rob": ["robert"],
    "bob": ["robert"],
    "dan": ["daniel"],
    "danny": ["daniel"],
    "dave": ["david"],
    "ed": ["edward", "eduardo", "eddie"],
    "eddie": ["edward", "eduardo", "ed"],
    "joe": ["joseph", "jose"],
    "jose": ["joseph"],
    "alex": ["alexander", "alejandro", "alexandra"],
    "sam": ["samuel", "samantha"],
    "chris": ["christopher", "christina", "christine"],
    "nick": ["nicholas", "nicolas"],
    "tom": ["thomas"],
    "tommy": ["thomas"],
    "will": ["william"],
    "bill": ["william"],
    "jim": ["james"],
    "jimmy": ["james"],
    "jake": ["jacob"],
    "tony": ["anthony", "antonio"],
    "steve": ["steven", "stephen"],
    "andy": ["andrew", "andrea"],
    "drew": ["andrew"],
    "ben": ["benjamin"],
    "liz": ["elizabeth"],
    "beth": ["elizabeth"],
    "kate": ["katherine", "kathryn", "catherine"],
    "katie": ["katherine", "kathryn", "catherine"],
    "jen": ["jennifer"],
    "jenny": ["jennifer"],
    "meg": ["megan", "margaret"],
    "maggie": ["margaret"],
    "sue": ["susan", "suzanne"],
    "pat": ["patricia", "patrick"],
    "rick": ["richard", "ricardo"],
    "dick": ["richard"],
    "rich": ["richard"],
    "ted": ["theodore", "edward"],
    "theo": ["theodore"],
    "max": ["maxwell", "maximilian"],
    "charlie": ["charles"],
    "chuck": ["charles"],
    "greg": ["gregory"],
    "tim": ["timothy"],
    "jon": ["jonathan", "john"],
    "johnny": ["john", "jonathan"],
    "larry": ["lawrence"],
    "terry": ["terrence", "teresa"],
    "jerry": ["gerald", "jerome"],
    "ray": ["raymond"],
    "ron": ["ronald"],
    "don": ["donald"],
    "doug": ["douglas"],
    "jeff": ["jeffrey"],
    "josh": ["joshua"],
    "zach": ["zachary"],
    "zack": ["zachary"],
    "nate": ["nathan", "nathaniel"],
    "lex": ["alexis", "alexander"],
    "ash": ["ashley", "ashton"],
    "jay": ["jason", "james"],
    "bri": ["brianna", "brian"],
    "tiff": ["tiffany"],
    "vince": ["vincent"],
    "vic": ["victor", "victoria"],
}

# Build reverse mapping (legal name -> nicknames)
LEGAL_TO_NICKNAME = {}
for nickname, legal_names in NICKNAME_MAP.items():
    for legal in legal_names:
        if legal not in LEGAL_TO_NICKNAME:
            LEGAL_TO_NICKNAME[legal] = []
        if nickname not in LEGAL_TO_NICKNAME[legal]:
            LEGAL_TO_NICKNAME[legal].append(nickname)


def normalize_name(name: str) -> str:
    """Normalize a name for comparison."""
    if not name:
        return ""
    # Remove extra whitespace, lowercase
    name = " ".join(name.lower().split())
    # Remove common suffixes
    name = re.sub(r'\s+(jr|sr|ii|iii|iv)\.?$', '', name)
    return name


def get_first_name(name: str) -> str:
    """Extract first name from full name."""
    parts = normalize_name(name).split()
    return parts[0] if parts else ""


def get_last_name(name: str) -> str:
    """Extract last name from full name."""
    parts = normalize_name(name).split()
    return parts[-1] if len(parts) > 1 else ""


def get_name_variations(first_name: str) -> List[str]:
    """Get all possible variations of a first name."""
    first_lower = first_name.lower()
    variations = {first_lower}
    
    # Add nickname mappings
    if first_lower in NICKNAME_MAP:
        variations.update(NICKNAME_MAP[first_lower])
    
    # Add reverse mappings (if this is a legal name, get nicknames)
    if first_lower in LEGAL_TO_NICKNAME:
        variations.update(LEGAL_TO_NICKNAME[first_lower])
    
    # Also check if any legal name starts with our name
    for legal, nicks in LEGAL_TO_NICKNAME.items():
        if legal.startswith(first_lower) and len(first_lower) >= 3:
            variations.add(legal)
            variations.update(nicks)
    
    return list(variations)


def similarity_score(s1: str, s2: str) -> float:
    """Calculate similarity between two strings (0-1)."""
    return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()


def match_employee_to_cv_name(
    employee_name: str,
    cv_names: List[str],
    threshold: float = 0.6
) -> Tuple[Optional[str], float, str]:
    """
    Match an employee name to the best CV name.
    
    Returns: (matched_cv_name, confidence_score, match_reason)
    """
    if not employee_name or not cv_names:
        return None, 0.0, "no_input"
    
    emp_normalized = normalize_name(employee_name)
    emp_first = get_first_name(employee_name)
    emp_last = get_last_name(employee_name)
    emp_variations = get_name_variations(emp_first)
    
    best_match = None
    best_score = 0.0
    best_reason = "no_match"
    
    for cv_name in cv_names:
        cv_normalized = normalize_name(cv_name)
        cv_first = get_first_name(cv_name)
        cv_last = get_last_name(cv_name)
        
        # 1. Exact full name match
        if emp_normalized == cv_normalized:
            return cv_name, 1.0, "exact_match"
        
        # 2. Last name matches + first name variation
        if emp_last and cv_last and emp_last == cv_last:
            # Check if first names are variations
            cv_variations = get_name_variations(cv_first)
            if emp_first in cv_variations or cv_first in emp_variations:
                return cv_name, 0.95, "last_name_match_with_nickname"
            
            # Check similarity of first names
            first_sim = similarity_score(emp_first, cv_first)
            if first_sim > 0.7:
                if first_sim > best_score:
                    best_match = cv_name
                    best_score = first_sim
                    best_reason = "last_name_match_similar_first"
        
        # 3. First name is a known variation (regardless of last name)
        cv_variations = get_name_variations(cv_first)
        if emp_first in cv_variations or cv_first in emp_variations:
            # Check last name similarity
            if emp_last and cv_last:
                last_sim = similarity_score(emp_last, cv_last)
                if last_sim > 0.7:
                    score = 0.9 + (last_sim * 0.1)
                    if score > best_score:
                        best_match = cv_name
                        best_score = score
                        best_reason = "nickname_match_with_similar_last"
            else:
                # No last name to compare, but first name matches
                if 0.85 > best_score:
                    best_match = cv_name
                    best_score = 0.85
                    best_reason = "nickname_match_only"
        
        # 4. First name starts with same letters (min 3)
        if len(emp_first) >= 3 and len(cv_first) >= 3:
            if emp_first[:3] == cv_first[:3]:
                # Check if last names match
                if emp_last and cv_last and emp_last == cv_last:
                    if 0.88 > best_score:
                        best_match = cv_name
                        best_score = 0.88
                        best_reason = "prefix_match_same_last"
                elif emp_last and cv_last and similarity_score(emp_last, cv_last) > 0.8:
                    if 0.82 > best_score:
                        best_match = cv_name
                        best_score = 0.82
                        best_reason = "prefix_match_similar_last"
        
        # 5. Full name similarity check
        full_sim = similarity_score(emp_normalized, cv_normalized)
        if full_sim > threshold and full_sim > best_score:
            best_match = cv_name
            best_score = full_sim
            best_reason = "fuzzy_match"
    
    if best_score >= threshold:
        return best_match, best_score, best_reason
    
    return None, best_score, "below_threshold"


def build_name_mapping(
    employee_names: List[str],
    cv_names: List[str]
) -> Dict[str, Dict]:
    """
    Build a complete mapping between employee names and CV names.
    
    Returns dict of:
    {
        employee_name: {
            "cv_name": matched CV name or None,
            "confidence": float 0-1,
            "reason": str explaining match type
        }
    }
    """
    mapping = {}
    used_cv_names = set()
    
    # First pass: high confidence matches
    for emp_name in employee_names:
        cv_name, confidence, reason = match_employee_to_cv_name(
            emp_name, 
            [n for n in cv_names if n not in used_cv_names]
        )
        if confidence >= 0.85:
            mapping[emp_name] = {
                "cv_name": cv_name,
                "confidence": confidence,
                "reason": reason
            }
            if cv_name:
                used_cv_names.add(cv_name)
    
    # Second pass: lower confidence matches for remaining
    for emp_name in employee_names:
        if emp_name in mapping:
            continue
        cv_name, confidence, reason = match_employee_to_cv_name(
            emp_name,
            [n for n in cv_names if n not in used_cv_names],
            threshold=0.6
        )
        mapping[emp_name] = {
            "cv_name": cv_name,
            "confidence": confidence,
            "reason": reason
        }
        if cv_name and confidence >= 0.6:
            used_cv_names.add(cv_name)
    
    return mapping


def get_nps_for_employee_smart(
    employee_name: str,
    nps_lookup: Dict[str, dict],
    employee_aliases: List[str] = None
) -> Tuple[dict, str]:
    """
    Smart NPS lookup that handles nickname variations.
    
    Args:
        employee_name: The employee's name in employees_v2
        nps_lookup: Dict of {cv_name_lower: nps_data}
        employee_aliases: Optional list of known aliases
    
    Returns: (nps_data_dict, match_reason)
    """
    emp_normalized = normalize_name(employee_name)
    emp_first = get_first_name(employee_name)
    emp_last = get_last_name(employee_name)
    
    # 1. Try exact match first
    if emp_normalized in nps_lookup:
        return nps_lookup[emp_normalized], "exact_match"
    
    # 2. Try aliases if provided
    if employee_aliases:
        for alias in employee_aliases:
            alias_lower = normalize_name(alias)
            if alias_lower in nps_lookup:
                return nps_lookup[alias_lower], f"alias_match:{alias}"
    
    # 3. Get all variations of employee's first name
    emp_variations = get_name_variations(emp_first)
    
    # 4. Search through CV names
    for cv_name_lower, nps_data in nps_lookup.items():
        cv_first = get_first_name(cv_name_lower)
        cv_last = get_last_name(cv_name_lower)
        
        # Check if first names match via variations
        cv_variations = get_name_variations(cv_first)
        first_name_matches = (
            emp_first in cv_variations or 
            cv_first in emp_variations or
            emp_first == cv_first
        )
        
        if first_name_matches:
            # Check last name
            if emp_last and cv_last:
                if emp_last == cv_last:
                    return nps_data, f"nickname_match:{cv_name_lower}"
                if similarity_score(emp_last, cv_last) > 0.75:
                    return nps_data, f"nickname_similar_last:{cv_name_lower}"
            else:
                # No last name but first matches via nickname
                return nps_data, f"nickname_only:{cv_name_lower}"
        
        # 5. Check if starts with same prefix + same last name
        if len(emp_first) >= 3 and len(cv_first) >= 3:
            if emp_first[:3] == cv_first[:3] and emp_last == cv_last:
                return nps_data, f"prefix_match:{cv_name_lower}"
    
    return {}, "no_match"
