#!/usr/bin/env python3

import unittest

from parsequality import get_quality_scores

class ParseQualityTest(unittest.TestCase):
    def test_score(self):
        correct, partial, total = get_quality_scores()
        # More than 75% of frame arguments should be exact subtrees from the dependency parse
        self.assertTrue(correct/total > 0.75)
        # Subtrees from the dependency parse should match at more than 90% the frame arguments
        self.assertTrue(partial/total > 0.90)
