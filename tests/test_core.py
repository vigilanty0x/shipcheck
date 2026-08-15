import unittest
from diff_risk_scorer import score,probe
class T(unittest.TestCase):
 def test_low(self):self.assertEqual(score([{"path":"src/a","additions":1,"deletions":0}])["band"],"low")
 def test_sensitive(self):self.assertGreaterEqual(score([{"path":"src/a","additions":1,"deletions":0,"sensitive":True}])["score"],30)
 def test_invalid(self):self.assertFalse(score([{"path":"../x","additions":1,"deletions":0}])["ok"])
 def test_probe(self):self.assertTrue(probe()["ok"])
if __name__=="__main__":unittest.main()
