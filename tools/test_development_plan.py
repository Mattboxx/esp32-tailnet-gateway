"""Structural traceability checks for the development plan, not firmware tests."""
from pathlib import Path
import hashlib
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]


class DevelopmentPlanTests(unittest.TestCase):
    def test_all_master_sections_retained(self):
        source=(ROOT/'docs/MASTER-DEVELOPMENT-PROMPT.md').read_text(encoding='utf-8')
        headings={int(n) for n in re.findall(r'^#{1,3} (\d+)\.',source,re.M)}
        self.assertEqual(headings,set(range(31)))
        self.assertEqual(len(source.splitlines()),1603)
        # The archival mandate is not the editable plan: preserve every detail.
        self.assertEqual(hashlib.sha256((source.rstrip()+'\n').encode()).hexdigest(),
                         '4957bfde1a3c5e3808225c603acd6c4c55cbaccddbe3feb2e758db64d84a935d')

    def test_matrix_schema_and_statuses(self):
        source=(ROOT/'docs/FEATURE-IMPLEMENTATION-MATRIX.md').read_text(encoding='utf-8')
        rows=[line for line in source.splitlines() if re.match(r'^\| F\d\d \|',line)]
        self.assertEqual([r.split('|')[1].strip() for r in rows],[f'F{n:02}' for n in range(1,44)])
        statuses={'Da analizzare','Progettata','In sviluppo','Implementata','Testata offline',
                  'Testata su hardware','Pronta per release','Bloccata con motivazione'}
        for row in rows:
            cells=[c.strip() for c in row.strip('|').split('|')]
            self.assertEqual(len(cells),11,row)
            self.assertTrue(all(cells),row)
            self.assertIn(cells[5],statuses)
            self.assertNotEqual(cells[5],'Pronta per release','No qualified release in this checkpoint')

    def test_all_milestones_and_operating_files(self):
        roadmap=(ROOT/'docs/DEVELOPMENT-ROADMAP.md').read_text(encoding='utf-8')
        for version in range(14,20):self.assertRegex(roadmap,rf'(?m)^## 1\.{version} ')
        for name in ('AGENTS.md','GOALS.md','docs/NEXT-STEPS-FOR-AGENT.md',
                     'docs/VALIDATION-STATUS.md','docs/ARCHITECTURE-DECISIONS.md'):
            self.assertTrue((ROOT/name).is_file(),name)
        for subject in ('Device Registry','Smart Recovery','Network and Tailnet Health Monitor',
                        'Connectivity Diagnostics Assistant','temporary rules','Sanitized Diagnostic',
                        'Capability Manifest','Ethernet','Home Assistant','Headscale','SNMP'):
            self.assertIn(subject,roadmap)


if __name__=='__main__':unittest.main()
