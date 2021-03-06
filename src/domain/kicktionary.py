#!/usr/bin/env python3

"""
Kicktionary parser which only use the information from the annotations.
"""

import xml.etree.ElementTree as ET

import paths


def text_from_example(example_xml):
    text_parts = []
    if example_xml.text and example_xml.text.strip():
        text_parts.append(example_xml.text.strip())

    for part in example_xml:
        if part.text and part.text.strip():
            text_parts.append(part.text.strip())
        if part.tail and part.tail.strip():
            text_parts.append(part.tail.strip())

    join_sentence = ' '.join(text_parts)
    join_sentence = join_sentence.replace(' ,', ',')
    join_sentence = join_sentence.replace(' .', '.')
    join_sentence = join_sentence.replace(' :', ':')
    join_sentence = join_sentence.replace(' ;', ';')
    return join_sentence


def lang_examples(all_lus, lang):
    for lu_report in all_lus.findall('LU_REPORT'):
        lu = lu_report.find('LEXICAL-UNIT')

        # Not considering German examples
        if lu.get('lang') != lang:
            continue
        # Not considering adjectives and nouns lexical units
        # This also removes multi-word expressions such as 'marquer_contre_son_camp.i'
        if not lu.get('lu-id').endswith('.v'):
            continue

        frame = lu.get('frame')
        lemma = lu.get('lu-id').split('.')[0]

        for example in lu_report.findall('EXAMPLE'):
            sentence_text = text_from_example(example)
            yield frame, lemma, example, sentence_text


def kicktionary_frames(lang):
    all_lus = ET.ElementTree(file=str(paths.Paths.ALL_LUS))

    for frame, lemma, example, sentence_text in lang_examples(all_lus, lang=lang):
        subcategorization_frame = ET.Element('SYNTAX')
        for child in example:
            if child.tag == 'LU_REF':
                ET.SubElement(subcategorization_frame, 'VERB')

            elif child.tag == 'FE_REF':
                # TODO needs to detect other types such as PP or S_ING
                role = child.get('fe-idref').title()  # BEING_FREE -> Being_Free
                ET.SubElement(subcategorization_frame, 'NP', value=role)

        # A few sentences don't have any role assignments, we skip those
        if subcategorization_frame:
            yield frame, lemma, sentence_text, subcategorization_frame
