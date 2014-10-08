#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from collections import defaultdict
import unittest
import re
import os
import sys


import argguesser
from framenetallreader import FNAllReader
import paths
import options
from stats import stats_data
from framestructure import FrameInstance, Predicate, Arg


"""Fill the roles of some frames extracted from the syntactic parser output
using the annotated FrameNet data.
"""

def fill_gold_roles(frame_instances, annotation_file, parsed_conll_file, verbnet_classes, role_matcher):
    """Fills the roles of some frame instance arguments, when possible.
    Note: frame_instances must be sorted by sentence order.
    Note: frame_instances is altered, even if the final result is returned.
    
    :param frame_instances: The frames.
    :type frame_instances: FrameInstance List.
    :param verbnet_classes: The VerbNet lexicon, used to determine which frames
    from the corpus we should have extracted.
    :type verbnet_classes: Str Dict.
    """
    
    frames = defaultdict(lambda: defaultdict(list))
    for frame in frame_instances:
        # /path/to/stuff.conll -> stuff
        frames[frame.filename.stem][frame.sentence_id].append(frame)

    fn_reader = FNAllReader(
            add_non_core_args=False, keep_unannotated = True)
    
    previous_id = -1
    sentence_frames = []
    good_frames = 0
    for frame in fn_reader.iter_frames(annotation_file, parsed_conll_file):

        stats_data["args_instanciated"] += len(
            [x for x in frame.args if x.instanciated])
        
        for arg in frame.args:
            if not arg.instanciated: continue
            try:
                possible_roles = role_matcher.possible_vn_roles(
                    arg.role,
                    fn_frame=frame.frame_name,
                    vn_classes=verbnet_classes[frame.predicate.lemma])
            except Exception: continue
            if len(possible_roles) == 1:
                stats_data["args_annotated_mapping_ok"] += 1
            
        if frame.sentence_id != previous_id:
            # /path/to/stuff.xml -> stuff
            sentence_frames = frames[frame.filename.stem][frame.sentence_id]
            for extracted_frame in sentence_frames:
                correct_num_tags(extracted_frame, frame.sentence)
            previous_id = frame.sentence_id
        
        frame_found = False
        for extracted_frame in sentence_frames:
            # See if we have the two "same" frames
            if predicate_match(extracted_frame.predicate, frame.predicate):
                good_frames += 1
                handle_frame(extracted_frame, frame)
                frame_found = True
                break

        if not frame_found:
            num_args = len([x for x in frame.args if x.instanciated])
            if frame.predicate.lemma not in verbnet_classes:
                stats_data["frame_not_extracted_not_verbnet"] += 1
                stats_data["arg_not_extracted_not_verbnet"] += num_args

            stats_data["frame_not_extracted"] += 1
            stats_data["arg_not_extracted"] += num_args


    stats_data["frame_extracted_bad"] += len(list(frame_instances)) - good_frames
    stats_data["frame_extracted_good"] += good_frames
    
    # For LUCorpus, discard every frame for which there was no match
    if options.corpus_lu:
        frame_instances = [x for x in frame_instances if x.frame_name != ""]
        
    return frame_instances

def correct_num_tags(extracted_frame, original_sentence):
    """ Replace <num> tags by their real equivalents
    and update begin/end attributes where necessary.
    
    :param extracted_frame: The frame that contains <num> tags
    :type extracted_frame: FrameInstance
    :param original_sentence: The original unaltered sentence of the frame
    :type original_sentence: str
    
    """
    
    # We don't want to include "," in numbers since 3,300 is actually to
    # numbers: 3 and 300, separate by a comma
    p = re.compile('[0-9]+')
    numbers = p.findall(original_sentence)
    
    frame_replace_all(extracted_frame, "<num> , <num>", "<num>,<num>")
    frame_replace_all(extracted_frame, "<num> : <num>", "<num>:<num>")
    
    for number in numbers:
        frame_replace_one(extracted_frame, "<num>", number)


def frame_replace_one(frame, search, replace):
    """ Replace the first occurence of a word by another word in a frame """
    position = frame.sentence.find(search)
    if position == -1: return False
    
    offset = len(replace) - len(search)
    
    frame.sentence = frame.sentence.replace(search, replace, 1)
    
    if frame.predicate.begin > position:
        frame.predicate.begin += offset
        frame.predicate.end += offset
    for arg in frame.args:
        if arg.begin > position:
            arg.begin += offset
        elif arg.end > position:
            arg.text = arg.text.replace(search, replace, 1)
        if arg.end > position:
            arg.end += offset
    return True
    
def frame_replace_all(frame, search, replace):
    """ Replace every occurence of a word by another word in a frame"""
    if search in replace:
        raise Exception("frame_replace_all : cannot handle cases where :search"
            " is a substring of :replace")
    
    while frame_replace_one(frame, search, replace): pass

def predicate_match(predicate1, predicate2):
    """ Tells whether two predicates in the same sentence belongs to the same frame"""
    return predicate1.begin == predicate2.begin

def handle_frame(extracted_frame, annotated_frame):
    # Update the frame data
    extracted_frame.frame_name = annotated_frame.frame_name
    extracted_frame.arg_annotated = annotated_frame.arg_annotated
    extracted_frame.annotated = True
    
    good_args, partial_args = 0, 0
    
    # Update the argument roles and statistics
    for annotated_arg in annotated_frame.args:
        if not annotated_arg.instanciated: continue
        
        arg_found = False
        for extracted_arg in extracted_frame.args:
            score = match_score(extracted_arg, annotated_arg)
            if score == 1:
                good_args += 1
                extracted_arg.role = annotated_arg.role
                extracted_arg.annotated = True
                arg_found = True
                break
            elif score > 0.5:
                partial_args += 1
                extracted_arg.role = annotated_arg.role
                extracted_arg.annotated = True
                arg_found = True
                break
        if not arg_found:
            stats_data["arg_not_extracted"] += 1
    
    if extracted_frame.arg_annotated:
        stats_data["arg_extracted_good"] += good_args
        stats_data["arg_extracted_bad"] += (len(extracted_frame.args) - good_args - partial_args)
        stats_data["arg_extracted_partial"] += partial_args

def match_score(arg1, arg2):
    intersect = 1 + min(arg1.end, arg2.end) - max(arg1.begin, arg2.begin)
    sum_length = (1 + arg1.end - arg1.begin) + (1 + arg2.end - arg2.begin)
    return 2 * max(0, intersect) / sum_length

class RoleExtractorTest(unittest.TestCase):
    def test_num_replacements(self):
        initial_sentence = ("She tells me that the <num> , <num> people we helped find"
                            " jobs in <num> earned approximately $ <num>"
                            " million dollars .")
        final_sentence = ("She tells me that the 3,666 people we helped find"
                          " jobs in 1998 earned approximately $ 49"
                          " million dollars .")
                          
        initial_predicate = Predicate(64, 69, "earned", "earn")
        final_predicate = Predicate(56, 61, "earned", "earn")
        
        initial_args = [
            Arg(18, 62, "the <num> people we helped find jobs in <num>",
                "role1", True, "phrase_type"),
            Arg(71, 107, "approximately $ <num> million dollars",
                "role2", True, "phrase_type")
        ]
        final_args = [
            Arg(18, 54, "the 3,666 people we helped find jobs in 1998",
                "role1", True, "phrase_type"),
            Arg(62, 95, "approximately $ 49 million dollars",
                "role2", True, "phrase_type")
        ]
        words = []
        
        frame = FrameInstance(initial_sentence, initial_predicate, initial_args,
            words, "fn_frame_name")
        
        correct_num_tags(frame, final_sentence)
        self.assertEqual(frame.sentence, final_sentence)
        self.assertEqual(frame.predicate, final_predicate)
        self.assertEqual(frame.args, final_args)

if __name__ == "__main__":
    import verbnetreader
    from argguesser import ArgGuesser
    from rolematcher import VnFnRoleMatcher

    role_matcher = VnFnRoleMatcher(paths.VNFN_MATCHING)
    verbnet_classes = verbnetreader.VerbnetReader(paths.VERBNET_PATH).classes
    arg_guesser = ArgGuesser(verbnet_classes)

    frames = []
    for filename in FNAllReader.fulltext_parses():
        for frame in arg_guesser.frame_instances_from_file(filename):
            frames.append(frame)

    frames = fill_gold_roles(frames, verbnet_classes, role_matcher)

    print("\nExtracted {} correct and {} incorrect (non-annotated) frames.\n"
          "Did not extract {} annotated frames ({} had a predicate not in VerbNet).\n"
          "Extracted {} correct, {} partial-match and {} incorrect arguments.\n"
          "Did not extract {} annotated arguments ({} had a predicate not in VerbNet).\n".format(
          stats_data["frame_extracted_good"], stats_data["frame_extracted_bad"],
          stats_data["frame_not_extracted"], stats_data["frame_not_extracted_not_verbnet"],
          stats_data["arg_extracted_good"], stats_data["arg_extracted_partial"],
          stats_data["arg_extracted_bad"],
          stats_data["arg_not_extracted"], stats_data["arg_not_extracted_not_verbnet"]
    ))
