#!/usr/bin/env python3
# -*- coding: utf-8 -*-

""" Extract frames, predicates and arguments from a corpus, using only syntactic annotations """

import unittest
import paths
import pickle
import os

from framestructure import FrameInstance, Predicate, Word, Arg
import verbnetreader
from framenetparsedreader import FNParsedReader
from framenetallreader import FNAllReader
import options
from conllreader import SyntacticTreeBuilder
from verbnetprepclasses import all_preps
from argheuristic import find_args
import wordclassesloader


class ArgGuesser(FNParsedReader):
    """
    :var verbnet_index: VerbnetFrame Dict -- Used to know which predicates are in VerbNet.
    :var base_forms: str Dict -- The infinitives of the verbal forms we found in the corpus.
    :var filename: str -- The name of the current CoNLL file.
    """
    
    predicate_pos = ["MD", "VB", "VBD", "VBG", "VBN", "VBP", "VBZ"]

    subject_deprels = [
    "LGS", #Logical subject -> should we keep this (36 args) ?
    "SBJ", "SUB"
    ]
    
    non_core_deprels = [
    "DIR", "EXT", "LOC",
    "MNR", "PRP", "PUT", "TMP"
    ]
        
    args_deprels = subject_deprels + [
    "DIR",
    "BNF", #the 'for' phrase for verbs that undergo dative shift
    "DTV", #the 'to' phrase for verbs that undergo dative shift
    "OBJ", #direct or indirect object or clause complement
    "OPRD",#object complement
    "PRD", #predicative complement
    "VMOD"
    ]
    
    # Source : http://www.comp.leeds.ac.uk/ccalas/tagsets/upenn.html
    pos_conversions = {
    "$":"NP",
    "CD":"NP", #Cardinal number ("The three of us")
    "DT":"NP", #Determiner ("this" or "that")
    "JJ":"ADJ",
    "JJR":"NP", #Comparative
    "JJS":"NP", #Superlative
    "MD":"S", #Modal verb
    "NN":"NP", "NNP":"NP", "NNPS": "NP", "NNS":"NP",
    "NP":"NP", "NPS":"NP",
    "PP":"PP",
    "PRP":"NP",
    "RB":"ADV",
    "TO":"to S",
    "VB":"S", #Base form of a verb
    "VBD":"S", "VBG":"S_ING",
    "VBN":"ADJ", #Participe, as "fed" in "He got so fed up that..."
    "VBP":"S", "VBZ":"S",
    "WDT":"NP" #Relative determiners ("that what whatever which whichever")
    }
    
    acceptable_pt = ["NP", "PP", "S_ING", "S"]
    
    complex_pos = ["IN", "WP"]

    def __init__(self, verbnet_index):
        FNParsedReader.__init__(self)
        self.verbnet_index = verbnet_index
        
    def _handle_file(self, filename):
        """ Extracts frames from one file and iterate over them """
        self.load_file(filename)
        sentence_id = 0
        for sentence_id, tree in enumerate(self.sentence_trees()):
            for frame in self._handle_sentence(sentence_id, tree, filename):
                yield frame
            sentence_id += 1
    
    def _handle_sentence(self, sentence_id, tree, filename):
        """ Extracts frames from one sentence and iterate over them """
        for node in tree:
            # For every verb, looks for its infinitive form in verbnet, and
            # builds a new frame if it is found
            node.lemma = node.word.lower()
            if node.lemma in self.base_forms:
                node.lemma = self.base_forms[node.lemma]
            if not node.lemma in self.verbnet_index:
                continue

            if self._is_predicate(node):
                #Si deprel = VC, prendre le noeud du haut pour les args
                #Si un child est VC -> ne rien faire avec ce node
                predicate = Predicate(
                    node.begin_head, node.begin_head + len(node.word) - 1,
                    node.word, node.lemma)
                
                if options.heuristic_rules:
                    args = [self._nodeToArg(x, node) for x in find_args(node)]
                else:
                    args = self._find_args(node)

                args = [x for x in args if self._is_good_pt(x.phrase_type)]
                
                yield FrameInstance(
                    sentence=tree.flat(),
                    predicate=predicate,
                    args=args,
                    words=[Word(x.begin, x.end, x.pos) for x in tree],
                    frame_name="",
                    sentence_id=sentence_id,
                    filename=filename
                )
    
    def _is_good_pt(self, phrase_type):
        """ Tells whether a phrase type is acceptable for an argument """
        # If it contains a space, it has been assigned by _get_phrase_type
        if " " in phrase_type: return True
        
        return phrase_type in self.acceptable_pt
    
    def _find_args(self, node):
        """Returns every arguments of a given node.
        
        :param node: The node for which descendants are susceptible to be returned.
        :type node: SyntacticTreeNode.
        :returns: Arg List -- The resulting list of arguments.
        
        """
        
        base_node = node
        while base_node.deprel in ["VC", "CONJ", "COORD"]:
            base_node = base_node.father
        
        result = self._find_args_rec(node, node)
        if not base_node is node and base_node.pos in self.predicate_pos:
            result += self._find_args_rec(base_node, base_node)

        result = [x for x in result if x.text != "to"]

        return result
    
    def _find_args_rec(self, predicate_node, node):
        """Returns every arguments of a given node that is a descendant of another node.
        It is possible that one of the returned arguments corresponds
        to the second node itself.
        
        :param predicate_node: The node of which we want to obtain arguments.
        :type predicate_node: SyntacticTreeNode.
        :param node: The node for which descendants are susceptible to be returned.
        :type node: SyntacticTreeNode.
        :returns: Arg List -- The resulting list of arguments.
        
        """
        result = []
        for child in node.children:
            if self._is_arg(child, predicate_node):
                result.append(self._nodeToArg(child, predicate_node))
            elif not child.pos in self.predicate_pos:
                result += self._find_args_rec(predicate_node, child)
        return result
    
    def _overlap(self, node1, node2):
        return (node1.begin <= node2.begin_head + len(node2.word) - 1 and
            node1.end >= node2.begin_head)
    
    def _same_side(self, node, child, predicate):
        if node.begin_head < predicate.begin_head:
            return child.end < predicate.begin_head
        return child.begin > predicate.begin_head
    
    def _nodeToArg(self, node, predicate):
        """ Builds an Arg using the data of a node. """
        
        # Prevent arguments from overlapping over the predicate
        begin, end = node.begin, node.end
        text = node.flat()

        if self._overlap(node, predicate):
            begin, end = node.begin_head, node.begin_head + len(node.word) - 1
            for child in node.children:
                if self._same_side(node, child, predicate):
                    begin, end = min(begin, child.begin), max(end, child.end)
            root = node
            while root.father != None: root = root.father
            text = root.flat()[begin:end+1]
            
        return Arg(
            begin=begin,
            end=end,
            text=text,
            # If the argument isn't continuous, text will not be
            # a substring of frame.sentence
            role="",
            instanciated=True,
            phrase_type=self._get_phrase_type(node),
            annotated=False)
    
    def _get_phrase_type(self, node):
        #IN = Preposition or subordinating conjunction
        if node.pos == "IN":
            if node.word.lower() in all_preps: return "PP"
            return "S"
        # WP = Wh-pronoun
        if node.pos == "WP":
            return node.word.lower()+" S"
        
        if node.pos in self.pos_conversions:
            return self.pos_conversions[node.pos]
        return node.pos
    
    def _is_predicate(self, node):
        """Tells whether a node can be used as a predicate for a frame"""
        # Check part-of-speech compatibility
        if not node.pos in self.predicate_pos:
            return False
        
        # Check that this node is not an auxiliary
        if node.lemma in ["be", "do", "have", "will", "would"]:
            for child in node.children:
                if child.pos in self.predicate_pos and child.deprel == "VC":
                    return False    
        return True
    
    def _is_subject(self, node, predicate_node):
        """Tells whether node is the subject of predicate_node. This is only called
        when node is a brother of predicate_node.
        """
        return ((not node is predicate_node) and
                node.deprel in self.subject_deprels)
        
    def _is_arg(self, node, predicate_node):
        """Tells whether node is an argument of predicate_node. This is only called
        when node is a descendant of predicate_node.
        """
        return ((not node is predicate_node) and
                node.deprel in self.args_deprels)

class ArgGuesserTest(unittest.TestCase):
    def test_global(self):
        verbnet = verbnetreader.VerbnetReader(paths.VERBNET_PATH).frames_for_verb
        arg_guesser = ArgGuesser(verbnet)

        frames = []
        for filename in FNAllReader.fulltext_parses():
            frames.extend([x for x in arg_guesser._handle_file(filename)])

        num_args = 0
        
        for frame in frames:
            for arg in frame.args:
                self.assertTrue(arg.text != "")
                #self.assertEqual(frame.sentence[arg.begin:arg.end + 1], arg.text)
            num_args += len(frame.args)
        print(len(frames))
        print(num_args)
            
    def test_1(self):
        conll_tree = """1	The	The	DT	DT	-	2	NMOD	-	-
2	others	others	NNS	NNS	-	5	SBJ	-	-
3	here	here	RB	RB	-	2	LOC	-	-
4	today	today	RB	RB	-	3	TMP	-	-
5	live	live	VV	VV	-	0	ROOT	-	-
6	elsewhere	elsewhere	RB	RB	-	5	LOC	-	-
7	.	.	.	.	-	5	P	-	-"""
        treeBuilder = SyntacticTreeBuilder(conll_tree)
        tree = treeBuilder.build_syntactic_tree()
        args = [
            Arg(0, 20, "The others here today", "", True, "NP")
        ]
        
        verbnet = verbnetreader.VerbnetReader(paths.VERBNET_PATH).frames_for_verb
        arg_guesser = ArgGuesser(verbnet)

        self.assertEqual(arg_guesser._find_args(tree), args)

if __name__ == "__main__":
    unittest.main()
