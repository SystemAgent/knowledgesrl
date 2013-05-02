#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Parse FrameNet fulltext annotation into Frame, Arg and Predicate objects."""

import unittest
import xml.etree.ElementTree as ET
import os
import sys
from framestructure import *

class FulltextReader:

    """Class used to parse one file of the FrameNet fulltext corpus

    :var frames: Frame list of every frame collected
    
    """
    
    def __init__(self, filename):
        """Read a file and update the collected frames list.
        
        :param filename: Path to the file to read.
        :type filename: str.
        
        """
        root = ET.ElementTree(file=filename)
                
        # etree will add the xmlns string before every tag name
        self._xmlns = "{http://framenet.icsi.berkeley.edu}"

        self.frames = []
        #DEBUG
        self.num_ignored_layer = 0
        #DEBUG
        self.num_self_args = 0
        #DEBUG
        self.num_not_found = 0
        
        for sentence in root.findall(self._xmlns+"sentence"):
            self._parse_sentence(sentence)
            
    def _parse_sentence(self, sentence):
        """Handle the parsing of one sentence.
        
        :param sentence: XML representation of the sentence.
        :type sentence: xml.etree.ElementTree.Element.
        
        """
        
        text = sentence.findall(self._xmlns+"text")[0].text
        for potential_frame in sentence.findall(self._xmlns+"annotationSet[@luName]"):
            frame_type = potential_frame.attrib["luName"].split(".")[1]
            annotated = potential_frame.attrib["status"]
            
            # We keep only annotated verbal frames
            if frame_type == "v" and annotated != "UNANN":
                self._parse_frame(text, potential_frame)
                  
    def _parse_frame(self, sentence_text, frame):
        """Handle the parsing of one frame.
        
        :param sentence_text: Sentence in which the frame occurs.
        :type sentence_text: str.
        :param frame: XML representation of the frame
        :type frame: xml.etree.ElementTree.Element.
        
        """

        predicate = self._build_predicate(sentence_text, frame)
        if predicate == None: return
        
        args = self._build_args_list(sentence_text, frame, predicate)

        self.frames.append(Frame(sentence_text, predicate, args))
    
    def _build_args_list(self, sentence_text, frame, predicate):
        """Handle the collection of argument list.
        
        :param sentence_text: Sentence in which the frame occurs.
        :type sentence_text: str.
        :param frame: XML representation of the frame
        :type frame: xml.etree.ElementTree.Element.
        :param predicate: The predicate of the frame
        :type predicate: Predicate
        :returns: Argument list -- the built argument list
        """
        
        args = []
        rank = 1
        stop = False
        while not stop:
            arg_search_str = "{}layer[@name='FE'][@rank='{}']/*".format(
                self._xmlns, rank)
            phrase_search_str = "{}layer[@name='PT'][@rank='{}']/*".format(
                self._xmlns, rank)
            arg_data = frame.findall(arg_search_str)
            phrase_data = frame.findall(phrase_search_str)
            
            # Stop if we have reached a non argument-annotated layer
            if len(arg_data) == 0: break

            for arg in arg_data:
                stop,new_arg = self._build_arg(
                    sentence_text, frame, predicate, arg, phrase_data, rank)
                if new_arg != None:
                    args.append(new_arg)
                
            rank += 1
        return args
    
    def _build_arg(self, sentence_text, frame, predicate, arg, phrase_data, rank):
        # Checks wether the argument is instanciated
        if "itype" in arg.attrib:
            return False,Arg(0, -1, "", arg.attrib["name"], False, "")
        else:
            # Stop if we have reached a non phrase-type-annotated layer
            # with at least one instanciated argument
            if len(phrase_data) == 0:
                print("WARNING: ignored layer {} of frame {} in {}".format(
                    rank, predicate.lemma, sentence_text), file=sys.stderr)
                #DEBUG
                self.num_ignored_layer += 1
                return True,None
                           
            arg_start = int(arg.attrib["start"])
            arg_end = int(arg.attrib["end"])
            
            phrase_found = False
            phrase_type = ""
            for phrase in phrase_data:
                phrase_found = (
                    int(phrase.attrib["start"]) == arg_start and
                    int(phrase.attrib["end"]) == arg_end)
                if phrase_found:
                    phrase_type = phrase.attrib["name"]
                    break
                    
            if phrase_found:
                return False,Arg(
                    arg_start, arg_end,
                    sentence_text[arg_start:(arg_end + 1)],
                    arg.attrib["name"], True, phrase_type)
            else:
                # Check wether this is some strange case where 
                # the predicate is also an argument
                phrase_found = (
                    arg_start == predicate.begin and
                    arg_end == predicate.end)
                if phrase_found:
                    #DEBUG
                    self.num_self_args += 1
                    print("WARNING: at layer {} of frame {} in {}"\
                        " marked {} as NI".format(
                            rank, predicate.lemma, sentence_text, 
                            sentence_text[arg_start:(arg_end + 1)]), 
                        file=sys.stderr)
                    return False,Arg(0, -1, "",  arg.attrib["name"], False, "")
                else:
                    print("WARNING: at layer {} of frame {} in {}"\
                        " could not find phrase type of {}".format(
                            rank, predicate.lemma, sentence_text, 
                            sentence_text[arg_start:(arg_end + 1)]), 
                        file=sys.stderr)
                    #DEBUG
                    self.num_not_found += 1
                    return False,None
    
    def _build_predicate(self, sentence_text, frame):
        """Handle the collection of the predicate data.
        
        :param sentence_text: Sentence in which the frame occurs.
        :type sentence_text: str.
        :param frame: XML representation of the frame
        :type frame: xml.etree.ElementTree.Element.
        :returns: Predicate -- the built predicate
        """
        predicate_lemma = frame.attrib["luName"].split(".")[0]
        predicate_data = frame.findall(self._xmlns+"layer[@name='Target']")[0]
        
        # This test handles the only self-closed layer tag that exists in the corpus
        if len(predicate_data) == 0:
            print("WARNING: frame ignored in {}".format(sentence_text), file=sys.stderr)
            return
        else:
            predicate_data = predicate_data[0]
        
        predicate_start = int(predicate_data.attrib["start"])
        predicate_end = int(predicate_data.attrib["end"])
        return Predicate(
            predicate_start, 
            predicate_end,
            sentence_text[predicate_start:(predicate_end + 1)],
            predicate_lemma)
            
            
class FulltextReaderTest(unittest.TestCase):

    """Unit test class"""
    
    def setUp(self):
        self.expected_values = {
            "LUCorpus-v0.3__AFGP-2002-602187-Trans.xml":(50,133),
            "LUCorpus-v0.3__AFGP-2002-600045-Trans.xml":(82,205),
            "LUCorpus-v0.3__20000416_xin_eng-NEW.xml":(40,108),
            "ANC__HistoryOfGreece.xml":(251,715),
            "Miscellaneous__SadatAssassination.xml":(11,40),
            "ANC__IntroOfDublin.xml":(84,208),
            "ANC__110CYL200.xml":(34,83),
            "KBEval__parc.xml":(57,151),
            "LUCorpus-v0.3__wsj_2465.xml":(70,182),
            "NTI__LibyaCountry1.xml":(81,242),
            "NTI__SouthAfrica_Introduction.xml":(105,299),
            "Miscellaneous__Hound-Ch14.xml":(20,43),
            "NTI__Iran_Introduction.xml":(125,320),
            "PropBank__AetnaLifeAndCasualty.xml":(12,37),
            "PropBank__ElectionVictory.xml":(57,156),
            "LUCorpus-v0.3__ENRON-pearson-email-25jul02.xml":(6,12),
            "KBEval__atm.xml":(101,280),
            "ANC__110CYL068.xml":(61,163),
            "KBEval__lcch.xml":(185,517),
            "NTI__Iran_Chemical.xml":(229,655),
            "LUCorpus-v0.3__IZ-060316-01-Trans-1.xml":(86,209),
            "ANC__110CYL070.xml":(26,71),
            "LUCorpus-v0.3__SNO-525.xml":(24,55),
            "LUCorpus-v0.3__wsj_1640.mrg-NEW.xml":(41,96),
            "LUCorpus-v0.3__CNN_ENG_20030614_173123.4-NEW-1.xml":(51,121),
            "LUCorpus-v0.3__artb_004_A1_E1_NEW.xml":(14,40),
            "LUCorpus-v0.3__20000424_nyt-NEW.xml":(5,14),
            "LUCorpus-v0.3__enron-thread-159550.xml":(67,197),
            "NTI__Iran_Missile.xml":(242,657),
            "ANC__112C-L013.xml":(41,100),
            "LUCorpus-v0.3__20000415_apw_eng-NEW.xml":(37,99),
            "ANC__EntrepreneurAsMadonna.xml":(71,183),
            "KBEval__MIT.xml":(78,207),
            "LUCorpus-v0.3__20000419_apw_eng-NEW.xml":(25,61),
            "NTI__Kazakhstan.xml":(26,75),
            "ANC__110CYL072.xml":(20,51),
            "KBEval__cycorp.xml":(12,31),
            "KBEval__Stanford.xml":(46,122),
            "SemAnno__Text1.xml":(14,49),
            "NTI__Syria_NuclearOverview.xml":(101,281),
            "PropBank__PolemicProgressiveEducation.xml":(144,362),
            "LUCorpus-v0.3__artb_004_A1_E2_NEW.xml":(16,42),
            "LUCorpus-v0.3__CNN_AARONBROWN_ENG_20051101_215800.partial-NEW.xml":(93,238),
            "C-4__C-4Text.xml":(24,67),
            "fullText.xsl":(0,0),
            "LUCorpus-v0.3__602CZL285-1.xml":(24,64),
            "NTI__Taiwan_Introduction.xml":(50,136),
            "KBEval__Brandeis.xml":(23,56),
            "NTI__NorthKorea_ChemicalOverview.xml":(109,285),
            "PropBank__TicketSplitting.xml":(92,238),
            "ANC__IntroHongKong.xml":(44,104),
            "ANC__WhereToHongKong.xml":(160,395),
            "ANC__HistoryOfLasVegas.xml":(191,524),
            "NTI__Russia_Introduction.xml":(62,159),
            "NTI__WMDNews_042106.xml":(105,282),
            "LUCorpus-v0.3__sw2025-ms98-a-trans.ascii-1-NEW.xml":(148,318),
            "NTI__workAdvances.xml":(45,124),
            "NTI__WMDNews_062606.xml":(167,449),
            "LUCorpus-v0.3__20000410_nyt-NEW.xml":(24,70),
            "LUCorpus-v0.3__AFGP-2002-600002-Trans.xml":(192,505),
            "NTI__Iran_Biological.xml":(142,359),
            "PropBank__LomaPrieta.xml":(164,396),
            "LUCorpus-v0.3__20000420_xin_eng-NEW.xml":(20,52),
            "ANC__StephanopoulosCrimes.xml":(60,164),
            "NTI__ChinaOverview.xml":(72,204),
            "QA__IranRelatedQuestions.xml":(439,1154),
            "NTI__NorthKorea_Introduction.xml":(128,355),
            "KBEval__utd-icsi.xml":(107,259),
            "NTI__NorthKorea_NuclearOverview.xml":(284,767),
            "NTI__NorthKorea_NuclearCapabilities.xml":(60,160),
            "ANC__110CYL069.xml":(1,2),
            "ANC__110CYL067.xml":(30,67),
            "ANC__IntroJamaica.xml":(111,287),
            "ANC__HistoryOfJerusalem.xml":(183,501),
            "NTI__BWTutorial_chapter1.xml":(177,446),
            "KBEval__LCC-M.xml":(90,246),
            "Miscellaneous__Hijack.xml":(6,15),
            "NTI__Iran_Nuclear.xml":(215,610),
            "PropBank__BellRinging.xml":(138,342)
            }
        """Total : 18072 arguments in 6828 frames"""
        
        self.tested_frames = [
            Frame(
                "Rep . Tony Hall , D- Ohio , urges the United Nations to allow"+\
                " a freer flow of food and medicine into Iraq .", 
                Predicate(28, 32, "urges", "urge"),
                [
                    Arg(34, 51, "the United Nations", "Addressee", True, "NP"),
                    Arg(53, 104,
                        "to allow a freer flow of food and medicine into Iraq", 
                        "Content", True, "VPto"),
                    Arg(0, 26, "Rep . Tony Hall , D- Ohio", "Speaker", True, "NP")
                ] ),
            Frame(
                "Rep . Tony Hall , D- Ohio , urges the United Nations to allow"+\
                " a freer flow of food and medicine into Iraq .", 
                 Predicate(56, 60, "allow", "allow"),
                 [
                    Arg(62, 104, 
                        "a freer flow of food and medicine into Iraq",
                        "Action", True, "NP"),
                    Arg(34, 51, "the United Nations", "Grantee", True, "NP"),
                    Arg(0, -1, "", "Grantor", False, "")
                 ] ) ]
            

    def test_global(self):        
        """Checks that no exception is raised and that
        no obvious errors occurs while parsing the whole corpus
        
        """

        basepath = "../data/fndata-1.5/fulltext/"
        
        #DEBUG
        total_num_ignored_layer = 0
        #DEBUG
        total_num_self_args = 0
        #DEBUG
        total_num_not_found = 0
        
        for filename in self.expected_values.keys():
            #print("Parsing "+filename)
            reader = FulltextReader(basepath+filename)

            # Nothing is empty and begins/ends are coherents
            arg_num = 0
            for frame in reader.frames:
                self.assertNotEqual(frame.predicate.text, "")
                self.assertEqual(
                    frame.predicate.text, 
                    frame.sentence[frame.predicate.begin:(frame.predicate.end + 1)])
                    
                arg_num += len(frame.args)
                last_arg = None
                for arg in frame.args:
                    # Instanciated arguments must contain something
                    self.assertTrue(arg.text != "" or arg.instanciated == False)
                    # Begin, end and text must be coherent
                    self.assertEqual(
                        arg.text, 
                        frame.sentence[arg.begin:(arg.end + 1)])
                    # The argument order must be correct (uninstanciated args last)
                    self.assertTrue(
                        last_arg == None or # Nothing to test or
                        (
                            # begin after the previous arg's begin (or not instanciated) and
                            (last_arg.begin <= arg.begin or arg.instanciated == False) and
                            # no instanciated args allowed after an uninstanciated arg
                            (arg.instanciated == False or last_arg.instanciated == True)
                        )
                    )  
                    last_arg = arg   
                            
            # The total number of frames and args is correct
            (good_frame_num, good_arg_num) = self.expected_values[filename]
            self.assertEqual(len(reader.frames), good_frame_num)
            self.assertEqual(arg_num, good_arg_num)
        
            print("Found {} frames and {} arguments: ok".format(
                len(reader.frames), arg_num))
        
        #DEBUG        
        print(total_num_ignored_layer, total_num_self_args, total_num_not_found)
        #138 5 14

    def test_specific_frames(self):
        """Checks that some particular frames are correctly parsed"""
        path = "../data/fndata-1.5/fulltext/LUCorpus-v0.3__20000424_nyt-NEW.xml"
        reader = FulltextReader(path)
        self.assertEqual(reader.frames[0], self.tested_frames[0])
        self.assertEqual(reader.frames[1], self.tested_frames[1])
        
if __name__ == "__main__":
    unittest.main()

