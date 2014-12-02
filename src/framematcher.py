#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Match VerbnetFrameOccurrence to appropriate VerbNetOfficialFrame syntax

Based on the 2004 Swier & Stevenson paper: Unsupervised Semantic Role Labeling.

The way frame matching works in Swier&Stevenson 2004 paper is not completely
specified: what happens when VerbNet frame is longer than FrameNet's frame?

Currently, we don't extract any slot when a non-match appears: while it can
make sense to omit objects at the end, it doesn't to omit at the beginning and
take at the end: this could result in a totally different syntactic
construction. But I could be wrong!

For example, if you have in FrameNet "NP V with NP", and VerbNet contains "NP V
NP with NP", what do you do? We decided, for now, to only match the syntactic
subject.
"""

from verbnetframe import ComputeSlotTypeMixin, VerbnetFrameOccurrence
from verbnetrestrictions import VNRestriction


class FrameMatcher():
    """Handle frame matching for a given frame that we want to annotate.

    :var frame_occurrence: VerbnetFrameOccurrence -- The frame to annotate
    :var best_score: int -- The best score encountered among all the matches
    :var best_data: (VerbnetOfficialFrame, int List) List -- The frames that
        achieved this best score + the mapping between the slots of
    :frame_occurrence and these verbnet frames
    :var algo: str -- The algorithm that we want to use

    """

    def __init__(self, frame_occurrence, algo):
        self.frame_occurrence = frame_occurrence
        self.algo = algo

        self.best_score = 0
        self.best_data = []
        self.best_classes = set()

    def handle_semantic_restrictions(self, restr_data):
        """Keep only frames for which the syntactic restriction are
        the best matched

        :param restr_data: The gathered relations between restrictions and words
        :type restr_data: (VNRestriction -> (str Counter)) NoHashDefaultDict

        """

        # Nothing to do if no matching have been done yet.
        # Returns early to avoid taking the max of an empty list.
        if len(self.best_data) == 0:
            return

        scores = [self.frame_semantic_score(x, restr_data) for x in self.best_data]
        assert len(scores) == len(self.best_data)

        self.best_data = [data_part for data_part, score in zip(self.best_data, scores)
                          if score == max(scores)]

    def frame_semantic_score(self, frame_data, semantic_data):
        """For a given frame from VerbNet, compute a semantic score between
        this frame and the headwords of the real frame associated with
        FrameMatcher.

        :param frame_data: The frame and the associated mapping
        :type frame_data: (VerbnetOfficialFrame, int List)
        :param semantic_data: The gathered relations between restrictions and words
        :type semantic_data: (VNRestriction -> (str Counter)) NoHashDefaultDict

        """

        frame, mapping = frame_data
        score = 0
        for slot1, slot2 in enumerate(mapping):
            if slot2 is None:
                continue
            if slot2 >= len(frame.role_restrictions):
                continue

            word = self.frame_occurrence.headwords[slot1]
            restr = frame.role_restrictions[slot2]
            score += restr.match_score(word, semantic_data)

        return score

    def get_matched_restrictions(self):
        """Returns the list of restrictions for which we know a given word was
        a match. Only headwords of arguments for which we attributed exactly
        one possible role are taken into account. The restriction associated to
        them is the OR of restrictions associated to this slot in every
        possible frame.

        :returns: VNRestriction Dict -- a mapping between head words and the restriction they match
        """
        slots = self.possible_distribs()
        for i, slot in enumerate(slots):
            if slot is None or len(slot) != 1:
                continue

            restr = VNRestriction.build_empty()
            for frame, mapping in self.best_data:
                if mapping[i] is None:
                    continue
                elif mapping[i] >= len(frame.role_restrictions):
                    continue

                restr = VNRestriction.build_or(
                    restr,
                    frame.role_restrictions[mapping[i]])

            yield i, restr

    @staticmethod
    def _is_a_match(frame_occurrence_elem, frame_elem):
        """Tell wether two elements can be considered as a match

        frame_occurrence_elem is a seen element, while frame_elem can contain a
        set of possible elements, such as prepositions
        """

        if isinstance(frame_elem, set):
            return frame_occurrence_elem in frame_elem
        else:
            return frame_occurrence_elem == frame_elem

    def _matching_baseline(self, verbnet_frame, slots_associations):
        """ Matching algorithm that is the closest to the article's method """
        # As slots are not attributed in order, we need to keep a list
        # of the slots that have not been attributed yet
        available_slots = []
        num_match = 0

        for i, x in enumerate(verbnet_frame.slot_types):
            available_slots.append(
                {"slot_type": x, "pos": i, "prep": verbnet_frame.slot_preps[i]}
            )

        for slot_pos, slot_type in enumerate(self.frame_occurrence.slot_types):
            # For every slot, try to find a matching slot in available_slots
            i, matching_slot = -1, -1

            for test_slot_data in available_slots:
                # Could have used enumerate, but it looks better like this
                # as i is used after the loop
                i += 1

                # We want a slot that has the same type and the same prep
                # (or a list slot preps containing our preposition)
                if test_slot_data["slot_type"] != slot_type:
                    continue

                if (slot_type == ComputeSlotTypeMixin.slot_types["prep_object"] and
                    not FrameMatcher._is_a_match(
                        self.frame_occurrence.slot_preps[slot_pos],
                        test_slot_data["prep"])):
                    continue

                matching_slot = test_slot_data["pos"]
                break  # Stop at the first good slot we find

            if matching_slot != -1:
                del available_slots[i]  # Slot i has been attributed
                # TODO? we need to check that enough roles were given in VerbNet
                if verbnet_frame.num_slots > matching_slot:
                    slots_associations[slot_pos] = matching_slot

                num_match += 1
        return num_match, slots_associations

    def _matching_sync_predicates(self, verbnet_frame, slots_associations):
        """ Stop the algorithm at the first mismatch encountered after the verb,
        restart at the verb's position if a mismatch is encountered before the
        verb """

        num_match = 0
        i, j = 0, 0
        index_v_in_frame_occurrence = self.frame_occurrence.structure.index("V")
        index_v_in_official_frame = verbnet_frame.syntax.index(("V", None))
        slot_1, slot_2 = 0, 0
        num_slots_before_v_in_frame_occurrence = 0
        num_slots_before_v_in_official_frame = 0

        for elem in self.frame_occurrence.structure:
            if VerbnetFrameOccurrence._is_a_slot(elem):
                num_slots_before_v_in_frame_occurrence += 1
            elif elem == "V":
                break
        for elem, role in verbnet_frame.syntax:
            if role is not None:
                num_slots_before_v_in_official_frame += 1
            elif elem == "V":
                break

        while i < len(self.frame_occurrence.structure) and j < len(verbnet_frame.syntax):
            elem1 = self.frame_occurrence.structure[i]
            elem2, role2 = verbnet_frame.syntax[j]

            if FrameMatcher._is_a_match(elem1, elem2):
                if VerbnetFrameOccurrence._is_a_slot(elem1):
                    num_match += 1
                    # TODO this is probably fixed with the SYNTAX-based VN reader
                    # verbnet_frame can have more syntax than roles.This will
                    # for instance happen in the "NP V NP S_INF" syntax of
                    # want-32.1, where S_INF is given no role since it's part
                    # of the NP
                    if slot_2 < verbnet_frame.num_slots:
                        slots_associations[slot_1] = slot_2
                        slot_1, slot_2 = slot_1 + 1, slot_2 + 1
            # no match, but not seen the verb everywhere yet
            elif i < index_v_in_frame_occurrence or j < index_v_in_official_frame:
                # If we have not encountered the verb yet, we continue the matching
                # with everything that follows the verb
                # This is for instance to prevent a "NP NP V" construct
                # from interrupting the matching early
                i, j = index_v_in_frame_occurrence, index_v_in_official_frame
                slot_1 = num_slots_before_v_in_frame_occurrence
                slot_2 = num_slots_before_v_in_official_frame
            else:
                break

            i, j = i + 1, j + 1

        return num_match, slots_associations

    def _matching_stop_on_fail(self, verbnet_frame, slots_associations):
        """ Stop the algorithm at the first mismatch encountered """
        num_match = 0
        for elem1, elemrole2 in zip(self.frame_occurrence.structure, verbnet_frame.syntax):
            elem2, role2 = elemrole2
            if FrameMatcher._is_a_match(elem1, elem2):
                if VerbnetFrameOccurrence._is_a_slot(elem1):
                    num_match += 1
                    if num_match - 1 < verbnet_frame.num_slots:
                        slots_associations[num_match - 1] = num_match - 1
            else:
                break

        return num_match, slots_associations

    def new_match(self, verbnet_frame):
        """Compute the matching score and update the possible roles distribs

        :param verbnet_frame: frame to test.
        :type verbnet_frame: VerbnetOfficialFrame.

        """
        slots_associations = [None for x in range(self.frame_occurrence.num_slots)]

        # Consider 'that' as optional in english, eg.:
        # Tell him that S --> Tell him S
        import copy
        if verbnet_frame.has('that') and 'that' not in self.frame_occurrence.structure:
            verbnet_frame = copy.deepcopy(verbnet_frame)
            verbnet_frame.remove('that')

        if self.algo == "baseline":
            matching_function = self._matching_baseline
        elif self.algo == "sync_predicates":
            matching_function = self._matching_sync_predicates
        elif self.algo == "stop_on_fail":
            matching_function = self._matching_stop_on_fail
        else:
            raise Exception("Unknown matching algorithm : {}".format(self.algo))

        num_match, slots_associations = matching_function(verbnet_frame, slots_associations)

        # Score computation
        ratio_1 = num_match / self.frame_occurrence.num_slots
        if verbnet_frame.num_slots == 0:
            ratio_2 = 1
        else:
            ratio_2 = num_match / verbnet_frame.num_slots
        score = int(100 * (ratio_1 + ratio_2))

        if score > self.best_score:
            # This frame is better than any previous one: reset everything
            self.best_data = []
            self.best_classes = set()

        if score >= self.best_score:
            # This frame is at least as good as the others: add its data
            self.best_score = score
            self.best_data.append((verbnet_frame, slots_associations))
            self.best_classes.add(verbnet_frame.vnclass)

    def possible_distribs(self):
        """Compute the lists of possible roles for each slots

        :returns: str set list -- The lists of possible roles for each slot
        """

        result = [set() for x in range(self.frame_occurrence.num_slots)]

        for verbnet_frame, mapping in self.best_data:
            for slot1, slot2 in enumerate(mapping):
                if slot2 is None:
                    continue

                # We want this to fail when roles get stored in a dictionary or a class
                assert all([type(s) == tuple for s in verbnet_frame.syntax])

                role = [role for elem, role in verbnet_frame.syntax if role is not None][slot2]
                result[slot1].add(role)

        return result
