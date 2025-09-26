# _list_structure.py
import os
import sys
import argparse
import re # For ANSI stripping

# Directories or files to generally ignore at any level
IGNORE_LIST = {
    '__pycache__',
    '.git',
    '.vscode',
    '.idea',
    'venv',
    '.env', # We can now control this via FORCE_INCLUDE_LIST
    'node_modules',
    '*.pyc', # Note: This will only ignore a literal file/dir named "*.pyc", not via globbing.
    '*.log', # Same as above.
    'db.sqlite3',
    '.DS_Store',
    'Thumbs.db',
    'staticfiles',
    'media',
    'list_structure.py', # Ignore this script itself
    'Pipfile',
    'Pipfile.lock',
    '.dockerignore',
    'Dockerfile',
    'docker-compose.yml',
    'PROJECT_STRUCTURE.md', # Ignore the output file this script generates
}

# Items to always include, overriding IGNORE_LIST and dotfile filtering
FORCE_INCLUDE_LIST = {
    '.env',
    '.env.example',
    '.dockerignore',
    '.gitattributes',
    '.gitignore', # A common dotfile you might want to see
}

# ANSI escape codes for colors
class Colors:
    BLUE = '\033[94m'   # For directories
    GREEN = '\033[92m'  # For files
    YELLOW = '\033[93m' # For (empty) on subdirectories
    RED = '\033[91m'    # For (empty) on project root
    ENDC = '\033[0m'    # Reset color
    DIM = '\033[2m'     # For pruned message

def should_include_item(item_name):
    """
    Determines if a file or directory should be included in the tree.
    - First, checks the FORCE_INCLUDE_LIST.
    - If not forced, applies the IGNORE_LIST and dotfile rules.
    """
    # Priority 1: Always include if in the force-include list
    if item_name in FORCE_INCLUDE_LIST:
        return True
    
    # Priority 2: Exclude if it's in the ignore list
    if item_name in IGNORE_LIST:
        return False
    
    # Priority 3: Exclude if it starts with a dot (and wasn't force-included)
    if item_name.startswith('.'):
        return False
        
    # If it passes all exclusion rules, include it
    return True

def generate_tree_lines(current_path, project_root_abs, current_depth, max_depth, is_last_item_stack):
    """
    Recursively generates lines for the directory tree.
    Sorts directories first, then files, both alphabetically (case-insensitive).
    """
    lines = []
    base_name = os.path.basename(current_path)

    # Determine prefix for the current item (├─, └─, etc.)
    prefix_parts = []
    for is_last in is_last_item_stack[:-1]:
        prefix_parts.append('    ' if is_last else '│   ')
    if is_last_item_stack: # Check if the stack is not empty
        prefix_parts.append('└── ' if is_last_item_stack[-1] else '├── ')
    prefix = "".join(prefix_parts)

    if os.path.isdir(current_path):
        dir_name_colored = f"{Colors.BLUE}{base_name}/{Colors.ENDC}"
        
        all_children_for_this_dir = []
        # Only try to list children if we are not yet at max_depth
        if current_depth < max_depth:
            try:
                items = os.listdir(current_path) # Get all items
            except OSError: # Permission denied, etc.
                items = []

            # Filter and sort directories (case-insensitive) using the helper function
            _filtered_dirs = [item for item in items if os.path.isdir(os.path.join(current_path, item)) and should_include_item(item)]
            dirs = sorted(_filtered_dirs, key=str.lower)

            # Filter and sort files (case-insensitive) using the helper function
            _filtered_files = [item for item in items if os.path.isfile(os.path.join(current_path, item)) and should_include_item(item)]
            files = sorted(_filtered_files, key=str.lower)
            
            all_children_for_this_dir = dirs + files
        
        empty_marker_colored = ""
        is_actually_empty = not all_children_for_this_dir and current_depth < max_depth

        if is_actually_empty:
            empty_marker_colored = f" {Colors.YELLOW}(empty){Colors.ENDC}"

        lines.append(f"{prefix}{dir_name_colored}{empty_marker_colored}")
        
        if current_depth < max_depth:
            for i, item_name in enumerate(all_children_for_this_dir):
                item_path = os.path.join(current_path, item_name)
                is_last_child = (i == len(all_children_for_this_dir) - 1)
                lines.extend(generate_tree_lines(item_path, project_root_abs, current_depth + 1, max_depth, is_last_item_stack + [is_last_child]))
        
        elif current_depth == max_depth:
            try:
                items_at_max_depth = os.listdir(current_path)
                # Use should_include_item to check for potential children
                potential_children_at_max_depth = [
                    item for item in items_at_max_depth 
                    if should_include_item(item) and \
                       (os.path.isdir(os.path.join(current_path, item)) or os.path.isfile(os.path.join(current_path, item)))
                ]
            except OSError:
                potential_children_at_max_depth = []

            if potential_children_at_max_depth:
                pruned_msg_stack = is_last_item_stack + [True] 
                pruned_prefix_parts = []
                for is_last in pruned_msg_stack[:-1]:
                    pruned_prefix_parts.append('    ' if is_last else '│   ')
                if pruned_msg_stack:
                    pruned_prefix_parts.append('└── ' if pruned_msg_stack[-1] else '├── ')
                
                pruned_prefix = "".join(pruned_prefix_parts)
                lines.append(f"{pruned_prefix}{Colors.DIM}... (contents pruned at max_depth={max_depth}){Colors.ENDC}")

    elif os.path.isfile(current_path):
        lines.append(f"{prefix}{Colors.GREEN}{base_name}{Colors.ENDC}")

    return lines

def generate_project_structure_output(startpath, max_depth=4):
    """Generates directory structure output (string for file, colored for screen)."""
    startpath_abs = os.path.abspath(startpath)
    project_root_name = os.path.basename(startpath_abs)
    
    ansi_escape_pattern = re.compile(r'\033\[[0-9;]*m')

    try:
        root_items = os.listdir(startpath_abs) # Get all root items
    except OSError:
        root_items = []

    # Filter and sort root directories (case-insensitive) using the helper function
    root_dirs = sorted(
        [item for item in root_items if os.path.isdir(os.path.join(startpath_abs, item)) and should_include_item(item)],
        key=str.lower
    )
    # Filter and sort root files (case-insensitive) using the helper function
    root_files = sorted(
        [item for item in root_items if os.path.isfile(os.path.join(startpath_abs, item)) and should_include_item(item)],
        key=str.lower
    )
    all_root_children = root_dirs + root_files

    header_screen = f"\n{Colors.BLUE}## Project Structure: {project_root_name}/{Colors.ENDC} (from: {startpath_abs})"
    screen_output_lines = [header_screen]

    root_display_colored = f"{Colors.BLUE}{project_root_name}/{Colors.ENDC}"
    root_display_plain = f"{project_root_name}/"

    if not all_root_children: 
        root_display_colored = f"{Colors.RED}{project_root_name}/ (empty){Colors.ENDC}"
        root_display_plain = f"{project_root_name}/ (empty)"
    
    screen_output_lines.append(root_display_colored)

    children_lines_colored = []
    if max_depth > 0:
        for i, item_name in enumerate(all_root_children):
            item_path = os.path.join(startpath_abs, item_name)
            is_last_child_in_root = (i == len(all_root_children) - 1)
            children_lines_colored.extend(generate_tree_lines(item_path, startpath_abs, 1, max_depth, [is_last_child_in_root]))
    
    screen_output_lines.extend(children_lines_colored)
    screen_output_string = "\n".join(screen_output_lines) + f"\n\n{Colors.DIM}--- Structure listing complete (max_depth={max_depth}) ---{Colors.ENDC}\n"

    header_file = f"## Project Structure: \n\n```text" #{project_root_name}/ (from: {startpath_abs})\n\n```text"
    file_output_lines = [header_file]
    file_output_lines.append(root_display_plain)
    
    children_lines_plain = [ansi_escape_pattern.sub('', line) for line in children_lines_colored]
    file_output_lines.extend(children_lines_plain)
    
    file_output_lines.append("```")
    file_output_lines.append(f"\n*Structure listing generated with `max_depth={max_depth}`.*\n")
    file_output_string = "\n".join(file_output_lines)
    
    return screen_output_string, file_output_string


if __name__ == "__main__":
    default_depth=6
    parser = argparse.ArgumentParser(description='List project directory structure, print to screen, and save to PROJECT_STRUCTURE.md.')
    parser.add_argument('project_root', type=str, nargs='?', default='.', help='Path to the root directory of the project (default: current directory).')
    parser.add_argument('--depth', type=int, default=default_depth, help=f'Maximum depth to traverse for children (default: {default_depth}). Root is level 0, its children are level 1, etc.')
    
    args = parser.parse_args()

    if not os.path.isdir(args.project_root):
        print(f"\n{Colors.RED}Error: Directory not found: {os.path.abspath(args.project_root)}{Colors.ENDC}\n", file=sys.stderr)
    else:
        output_filename = "_PROJECT_STRUCTURE.md"
        output_filepath = os.path.join(os.path.abspath(args.project_root), output_filename)
        
        screen_text, file_text = generate_project_structure_output(args.project_root, args.depth)
        
        print(screen_text)
        
        try:
            with open(output_filepath, 'w', encoding='utf-8') as f:
                f.write(file_text)
            print(f"{Colors.GREEN}Successfully saved project structure to {output_filepath}{Colors.ENDC}\n")
        except IOError as e:
            print(f"{Colors.RED}Error writing to file {output_filename} in {os.path.dirname(output_filepath)}: {e}{Colors.ENDC}\n", file=sys.stderr)
