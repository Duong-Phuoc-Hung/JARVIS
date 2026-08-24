import os
import sys
import glob
import ast
import re

test_files = glob.glob('tests/test_*.py')
print('Found %d test files.' % len(test_files))

total_tests = 0
tests_info = []

for tf in sorted(test_files):
    with open(tf, 'r', encoding='utf-8') as f:
        content = f.read()
    tree = ast.parse(content, filename=tf)
    
    file_tests = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
            file_tests += 1
            total_tests += 1
            assert_nodes = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
            
            tautological = []
            for a in assert_nodes:
                if isinstance(a.test, ast.Constant) and a.test.value in (True, 1, 'true'):
                    tautological.append(ast.unparse(a))
                elif isinstance(a.test, ast.Compare):
                    left = ast.unparse(a.test.left)
                    comparators = [ast.unparse(c) for c in a.test.comparators]
                    if any(left == c for c in comparators):
                        tautological.append(ast.unparse(a))
            
            raises_nodes = []
            for n in ast.walk(node):
                if isinstance(n, ast.With):
                    for item in n.items:
                        if 'raises' in ast.unparse(item.context_expr):
                            raises_nodes.append(ast.unparse(item.context_expr))
            
            doc = ast.get_docstring(node) or ''
            
            tests_info.append({
                'file': tf,
                'name': node.name,
                'line': node.lineno,
                'assert_count': len(assert_nodes),
                'raises_count': len(raises_nodes),
                'tautological': tautological,
                'doc': doc
            })
    print('%-35s: %2d test functions' % (tf, file_tests))

print('\nTotal test functions across all files: %d' % total_tests)
tautos = [t for t in tests_info if t['tautological']]
print('Tautological asserts found: %d' % len(tautos))
for t in tautos:
    print('  %s:%s (line %d) -> %s' % (t['file'], t['name'], t['line'], t['tautological']))

no_verification = [t for t in tests_info if t['assert_count'] == 0 and t['raises_count'] == 0]
print('Tests with NO asserts and NO pytest.raises: %d' % len(no_verification))
for t in no_verification:
    print('  %s:%s (line %d)' % (t['file'], t['name'], t['line']))
