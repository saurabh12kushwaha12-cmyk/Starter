import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class T(unittest.TestCase):
 def test_scenarios(self):
  for i in range(1,9):self.assertTrue((ROOT/'scenarios'/f'SCN-{i:03d}.json').exists())
 def test_data(self):
  self.assertGreaterEqual(len(json.loads((ROOT/'sample-data/customers.json').read_text())['customers']),3)
 def test_schemas(self):
  json.loads((ROOT/'schemas/telemetry-event.schema.json').read_text())
if __name__=='__main__':unittest.main()
