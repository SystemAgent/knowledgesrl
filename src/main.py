#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import framenetreader
from framestructure import *
import verbnetreader
import framematcher
import rolematcher
import probabilitymodel
import os
import sys
import getopt
import random
from collections import Counter

options = getopt.getopt(sys.argv[1:], "d:", ["fmatching-algo=", "core-args-only"])

corpus_path = "../data/fndata-1.5/fulltext/"
verbnet_path = "../data/verbnet-3.2/"
debug = False
n_debug = 20
framematcher.matching_algorithm = 1
core_args_only = False
probability_model = "predicate_slot"

for opt,value in options[0]:
    if opt == "-d":
        debug = True
        value = 0 if value == "" else int(value)
        if value > 0:
            n_debug = value
    if opt == "--fmatching-algo" and value == 0:
        framematcher.matching_algorithm = 0
    if opt == "--core-args-only":
        core_args_only = True

stats = {
    "files":0,
    "frames":0, "frames_kept":0,
    "args":0, "args_kept":0,
    "one_role":0, "no_role":0,
    "one_correct_role":0, "one_bad_role":0,
    "several_roles_ok":0, "several_roles_bad":0,
    "roles_conversion_impossible":0, "roles_conversion_ambiguous":0
}

ambiguous_mapping = {
    # Stats of ambiguous mapping when ignoring the FN frame given by the annotations
    "verbs":[], "args_total":0, "args":0,
    # Stats of ambiguous mapping remaining despite the FN frame given by the annotations
    "verbs_with_frame":[], "args_total_with_frame":0, "args_with_frame":0
}

errors = {
   "vn_parsing":[],
   "vn_missing":[],
   "unannotated_layer":[], "predicate_was_arg":[],
   "missing_phrase_type":[], "missing_predicate_data":[],
   "frame_without_slot":[],
   "impossible_role_matching":[],
   "ambiguous_role":[]
}

debug_data = []

def init_verbnet(path):
    print("Loading VerbNet data...", file=sys.stderr)
    reader = verbnetreader.VerbnetReader(path)
    errors["vn_parsing"] = reader.unhandled
    return reader.verbs, reader.classes

def init_fn_reader(path):
    reader = framenetreader.FulltextReader(corpus_path+filename, core_args_only)
    
    errors["unannotated_layer"] += reader.ignored_layers
    errors["predicate_was_arg"] += reader.predicate_is_arg
    errors["missing_phrase_type"] += reader.phrase_not_found
    errors["missing_predicate_data"] += reader.missing_predicate_data
    
    return reader
                    
def stats_quality():
    stats["roles_conversion_impossible"] = 0
    stats["roles_conversion_ambiguous"] = 0
    stats["one_correct_role"] = 0
    stats["several_roles_ok"] = 0
    stats["one_bad_role"] = 0
    stats["several_roles_bad"] = 0
    stats["one_role"] = 0
    stats["no_role"] = 0
    
    for good_frame, frame in zip(annotated_frames, vn_frames):    
        for i, slot in enumerate(frame.roles):
            if len(slot) == 0: stats["no_role"] += 1
            elif len(slot) == 1: stats["one_role"] += 1
            
            try:
                possible_roles = role_matcher.possible_vn_roles(
                    good_frame.args[i].role,
                    fn_frame=good_frame.frame_name,
                    vn_classes=verbnet_classes[good_frame.predicate.lemma]
                    )
            except rolematcher.RoleMatchingError as e:
                stats["roles_conversion_impossible"] += 1
                log_impossible_role_matching(filename, good_frame, i, e.msg)
                continue
  
            if len(possible_roles) > 1:
                stats["roles_conversion_ambiguous"] += 1
            elif next(iter(possible_roles)) in slot:
                if len(slot) == 1: stats["one_correct_role"] += 1
                else: stats["several_roles_ok"] += 1
            elif len(slot) >= 1:
                if len(slot) == 1: stats["one_bad_role"] += 1
                else: stats["several_roles_bad"] += 1
                    
        if debug and set() in distrib:
            log_debug_data(frame, converted_frame, matcher, distrib)
    
def stats_ambiguous_roles(frame, num_args):
    found_ambiguous_arg = False
    found_ambiguous_arg_2 = False
    for arg in frame.args:
        if not arg.instanciated: continue
        try:
            if len(role_matcher.possible_vn_roles(
                arg.role, vn_classes = verbnet_classes[frame.predicate.lemma]
            )) > 1:
                if not found_ambiguous_arg:
                    found_ambiguous_arg = True
                    ambiguous_mapping["verbs"].append(frame.predicate.lemma)
                    ambiguous_mapping["args_total"] += num_args
                ambiguous_mapping["args"] += 1

                log_ambiguous_role_conversion(filename, frame, arg)
                
                if len(role_matcher.possible_vn_roles(
                    arg.role,
                    fn_frame = frame.frame_name,
                    vn_classes = verbnet_classes[frame.predicate.lemma]
                )) > 1:
                    if not found_ambiguous_arg_2:
                        found_ambiguous_arg_2 = True
                        ambiguous_mapping["verbs_with_frame"].append(frame.predicate.lemma)
                        ambiguous_mapping["args_total_with_frame"] += num_args
                    ambiguous_mapping["args_with_frame"] += 1
        except rolematcher.RoleMatchingError:
            pass

def log_ambiguous_role_conversion(filename, frame, arg):
    errors["ambiguous_role"].append({
        "file":filename,
        "argument":arg.text,"fn_role":arg.role,"fn_frame":frame.frame_name,
        "predicate":frame.predicate.lemma,
        "predicate_classes":verbnet_classes[frame.predicate.lemma],
        "sentence":frame.sentence,
        "vn_roles":role_matcher.possible_vn_roles(
                arg.role, vn_classes = verbnet_classes[frame.predicate.lemma])
    })

def log_vn_missing(filename, frame):
    errors["vn_missing"].append({
        "file":filename,"sentence":frame.sentence,
        "predicate":frame.predicate.lemma,
    })

def log_frame_without_slot(filename, frame, converted_frame):
    errors["frame_without_slot"].append({
        "file":filename,"sentence":frame.sentence,
        "predicate":frame.predicate.lemma,
        "structure":converted_frame.structure
    })

def log_impossible_role_matching(filename, frame, i, msg):
    errors["impossible_role_matching"].append({
        "file":filename, "sentence":frame.sentence,
        "predicate":frame.predicate.lemma,
        "fn_role":frame.args[i].role,
        "fn_frame":frame.frame_name,
        "msg":msg
    })
      
def log_debug_data(frame, converted_frame, matcher, distrib):
    debug_data.append({
        "sentence":frame.sentence,
        "predicate":frame.predicate.lemma,
        "args":[x.text for x in frame.args],
        "vbclass":verbnet[frame.predicate.lemma],
        "structure":converted_frame.structure,
        "chosen_frames":matcher.best_frames,
        "result":distrib
    })
  
def display_stats():
    stats["several_roles"] = stats["args_kept"] - (stats["one_role"] + stats["no_role"])
    print(
        "\n\nFiles: {} - annotated frames: {} - annotated args: {}\n"
        "Frames with predicate in VerbNet: {} frames ({} args) \n\n"
        
        "Frame matching:\n"
        "{} args without possible role\n"
        "{} args with exactly one possible role\n"
        "\t{} correct\n"
        "\t{} not correct\n"
        "\t{} cases where we cannot conclude (no role mapping for "
        "any possible VerbNet class and this frame or several possible roles)\n"
        "{} args with multiple possible roles\n"
        "\t{} correct (correct role is in role list)\n"
        "\t{} not correct (correct role is not in role list)\n"
        "\t{} cases where we cannot conclude (no role mapping for "
        "any possible VerbNet class and this frame or several possible roles)\n\n"
        "Role conversion issues:\n"
        "\t{} args with several possible VerbNet roles\n"
        "\t{} args for which no mapping between FrameNet and VerbNet roles was found"
        "\n\n".format(
            stats["files"], stats["frames"], stats["args"],
            stats["frames_kept"], stats["args_kept"],
            
            stats["no_role"],
            
            stats["one_role"], stats["one_correct_role"], stats["one_bad_role"],
            stats["one_role"] - (stats["one_bad_role"] + stats["one_correct_role"]),
            
            stats["several_roles"], stats["several_roles_ok"], stats["several_roles_bad"],
            stats["several_roles"] - (stats["several_roles_ok"] + stats["several_roles_bad"]),
            stats["roles_conversion_ambiguous"],
            stats["roles_conversion_impossible"])
    )
    """print(
        "Ambiguous VerbNet roles:\n"
        "With FrameNet frame indication:\n"
        "\tArguments: {}\n"
        "\tFrames: {}\n"
        "\tTotal number of arguments in those frames: {}\n"
        "Without FrameNet frame indication:\n"
        "\tArguments: {}\n"
        "\tFrames: {}\n"
        "\tTotal number of arguments in those frames: {}\n".format(
            ambiguous_mapping["args_with_frame"], len(ambiguous_mapping["verbs_with_frame"]),
            ambiguous_mapping["args_total_with_frame"], ambiguous_mapping["args"],
            len(ambiguous_mapping["verbs"]), ambiguous_mapping["args_total"]
        )
        
    )"""
    """count_with_frame = Counter(ambiguous_mapping["verbs_with_frame"])
    print(
        "Verbs list :\n"
        "(verb) - (number of ambiguous args without frame indication)"
        " - (number of ambiguous args with frame indications)"
    )
    for v, n1 in Counter(ambiguous_mapping["verbs"]).most_common():
        n2 = count_with_frame[v] if v in count_with_frame else 0
        print("{:>12}: {:>3} - {:<3}".format(v, n1, n2))"""

def display_errors_num():
    print(
        "\n\nProblems :\n"
        "{} unhandled case were encoutered while parsing VerbNet\n"
        "Ignored {} frame for which predicate data was missing\n"
        "Ignored {} non-annotated layers in FrameNet\n"
        "Marked {} arguments which were also predicate as NI\n"
        "Could not retrieve phrase type of {} arguments in FrameNet\n"
        "Ignored {} FrameNet frames which predicate was not in VerbNet\n"
        "Ignored {} empty FrameNet frames\n"
        "Was not able to compare {} roles\n\n".format(
            len(errors["vn_parsing"]), len(errors["missing_predicate_data"]),
            len(errors["unannotated_layer"]), len(errors["predicate_was_arg"]),
            len(errors["missing_phrase_type"]), len(errors["vn_missing"]),
            len(errors["frame_without_slot"]), len(errors["impossible_role_matching"]))
    )

def display_error_details():
    #for data in errors["vn_parsing"]: print(data) 
    #for data in errors["missing_predicate_data"]: print(data) 
    #for data in errors["unannotated_layer"]: print(data) 
    #for data in errors["predicate_was_arg"]: print(data) 
    #for data in errors["missing_phrase_type"]: print(data) 
    #for data in errors["vn_missing"]: print(data)          
    #for data in errors["frame_without_slot"]: print(data)
    #for data in errors["impossible_role_matching"]: print(data)
    #for data in errors["ambiguous_role"]: print(data)
    pass

def display_debug(n):
    random.shuffle(debug_data)
    for i in range(0, n):
        print(debug_data[i]["sentence"])
        print("Predicate : "+debug_data[i]["predicate"])
        print("Structure : "+" ".join(debug_data[i]["structure"]))
        print("Arguments :")
        for arg in debug_data[i]["args"]:
            print(arg)
        print("VerbNet data : ")
        for vbframe in debug_data[i]["vbclass"]:
            print(vbframe)
        print("Chosen frames : ")
        for vbframe in debug_data[i]["chosen_frames"]:
            print(vbframe)
        print("Result : ")
        print(debug_data[i]["result"])
        print("\n\n")
        
verbnet, verbnet_classes = init_verbnet(verbnet_path)

print("Loading frames...", file=sys.stderr)

annotated_frames = []
vn_frames = []

for filename in sorted(os.listdir(corpus_path)):
    if not filename[-4:] == ".xml": continue
    print(filename, file=sys.stderr)

    if stats["files"] % 100 == 0 and stats["files"] > 0:
        print("{} {} {}".format(
            stats["files"], stats["frames"], stats["args"]), file=sys.stderr)   
     
    fn_reader = init_fn_reader(corpus_path + filename)

    for frame in fn_reader.frames:
        stats["args"] += len(frame.args)
        stats["frames"] += 1

        if not frame.predicate.lemma in verbnet:
            log_vn_missing(filename, frame)
            continue
        
        annotated_frames.append(frame)
        
        converted_frame = VerbnetFrame.build_from_frame(frame)
        converted_frame.compute_slot_types()
        vn_frames.append(converted_frame)
    stats["files"] += 1

print("Loading FrameNet and VerbNet roles associations...", file=sys.stderr)
role_matcher = rolematcher.VnFnRoleMatcher(rolematcher.role_matching_file)
model = probabilitymodel.ProbabilityModel()

print("Frame matching...", file=sys.stderr)
for good_frame, frame in zip(annotated_frames, vn_frames):
    num_instanciated = sum([1 if x.instanciated else 0 for x in good_frame.args])

    stats_ambiguous_roles(good_frame, num_instanciated)
    predicate = good_frame.predicate.lemma
         
    try:
        matcher = framematcher.FrameMatcher(predicate, frame)
    except framematcher.EmptyFrameError:
        log_frame_without_slot(filename, good_frame, frame)
        continue

    for test_frame in verbnet[predicate]:
        matcher.new_match(test_frame)       

    frame.roles = matcher.possible_distribs()
    
    for roles, slot_type, prep in zip(frame.roles, frame.slot_types, frame.slot_preps):
        if len(roles) == 1:
            model.add_data(slot_type, next(iter(roles)), prep, predicate)

    stats["args_kept"] += num_instanciated
    stats["frames_kept"] += 1
    
print("Frame matching stats...", file=sys.stderr) 

stats_quality()
display_stats()

print("Applying probabilistic model...", file=sys.stderr)
for frame in vn_frames:
    for i in range(0, len(frame.roles)):
        if len(frame.roles[i]) > 1:
            new_role = model.best_role(
                frame.roles[i], frame.slot_types[i], frame.slot_preps[i],
                frame.predicate, probability_model)
            if new_role != None:
                frame.roles[i] = set([new_role])

print("Final stats...", file=sys.stderr)   

stats_quality()
display_stats()

#display_errors_num()
#display_error_details()
if debug: display_debug(n_debug)


