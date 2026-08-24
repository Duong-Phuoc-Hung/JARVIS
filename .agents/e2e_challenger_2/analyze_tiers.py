import os
import glob
import ast
import re

test_files = glob.glob('tests/test_*.py')

def analyze_test_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    tree = ast.parse(content, filename=filepath)
    
    tests = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
            doc = ast.get_docstring(node) or ''
            
            # Count asserts
            assert_count = 0
            tautological_asserts = []
            assert_calls = []
            
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assert):
                    assert_count += 1
                    unparsed = ast.unparse(sub)
                    if isinstance(sub.test, ast.Constant) and sub.test.value in (True, 1, 'true'):
                        tautological_asserts.append(unparsed)
                    elif isinstance(sub.test, ast.Compare):
                        left = ast.unparse(sub.test.left)
                        comps = [ast.unparse(c) for c in sub.test.comparators]
                        if any(left == c for c in comps):
                            tautological_asserts.append(unparsed)
                    assert_calls.append(unparsed)
                elif isinstance(sub, ast.Call):
                    func_name = ast.unparse(sub.func)
                    if 'assert' in func_name.lower():
                        assert_count += 1
                        unparsed = ast.unparse(sub)
                        if 'assertTrue(True)' in unparsed or 'assertEqual(1, 1)' in unparsed:
                            tautological_asserts.append(unparsed)
                        assert_calls.append(unparsed)
                elif isinstance(sub, ast.With):
                    for item in sub.items:
                        expr = ast.unparse(item.context_expr)
                        if 'raises' in expr:
                            assert_count += 1
                            assert_calls.append(expr)
            
            # Extract features referenced
            features_found = re.findall(r'F-\d{2}', doc + ' ' + content[node.lineno:node.end_lineno if hasattr(node, 'end_lineno') else node.lineno+50])
            tier_found = re.findall(r'Tier\s*[1-4]|tier[1-4]', node.name + ' ' + doc, re.IGNORECASE)
            
            tests.append({
                'name': node.name,
                'line': node.lineno,
                'doc': doc.split('\n')[0] if doc else '',
                'assert_count': assert_count,
                'tautological': tautological_asserts,
                'features': list(set(features_found)),
                'tier': list(set(tier_found)),
                'assert_samples': assert_calls[:3]
            })
    return tests

all_results = {}
total_asserts = 0
total_tests = 0
all_features_found = set()

for tf in sorted(test_files):
    tests = analyze_test_file(tf)
    all_results[tf] = tests
    file_asserts = sum(t['assert_count'] for t in tests)
    total_asserts += file_asserts
    total_tests += len(tests)
    for t in tests:
        all_features_found.update(t['features'])
    print(f'File: {tf:32s} | Tests: {len(tests):2d} | Assertions: {file_asserts:3d}')

print('=' * 60)
print(f'Total Tests: {total_tests}')
print(f'Total Assertions across all tests: {total_asserts}')
print(f'Average Assertions per Test: {total_asserts / total_tests:.2f}')
