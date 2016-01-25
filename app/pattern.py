import string
import numpy as np
import pandas
from enum import Enum

from app.generator import Generator, Ontology
from app.utility import NLPUtility, Utility, Printer

class Constructor:
	def __init__(self, nlp, user_stories, matrix):
		self.nlp = nlp
		self.user_stories = user_stories
		self.weights = matrix['sum'].reset_index().values.tolist()

	def make(self, ontname, threshold, link):
		weighted_tokens = WeightAttacher.make(self.user_stories, 
self.weights)
		
		self.onto = Ontology(ontname, self.user_stories)
		self.prolog = Ontology(ontname, self.user_stories)

		pf = PatternFactory(self.onto, self.prolog, weighted_tokens)
		self.onto = pf.make_patterns(self.user_stories, threshold)
		self.prolog = pf.prolog

		if link:
			self.link_to_story(self.onto.classes, self.user_stories)
			
		#for c in self.onto.classes:		
		#	print("\"" + c.name + "\"", "\"" + c.parent + "\"")

		g = Generator(self.onto.classes, self.onto.relationships)
		g_prolog = Generator(self.prolog.classes, self.prolog.relationships, False)

		return g.prt(self.onto), g_prolog.prt(self.prolog), self.onto, self.prolog

	def link_to_story(self, classes, stories):	
		used_stories = []

		for cl in classes:
			for story in cl.stories:
				if story >= 0:
					s = self.get_story(int(story), stories)
					part_name = self.get_parts(cl.name, s)

					for part in part_name:
						n = s.txtnr() + part
						self.onto.get_class_by_name(-1, n, s.txtnr())
						self.onto.new_relationship(-1, cl.name, cl.name + 'OccursIn' + n, n)
						self.prolog.new_relationship(-1, cl.name, part, s.txtnr())

					used_stories.append(s.txtnr())
		
		for story in used_stories:
			self.onto.get_class_by_name(-1, story, 'UserStory')

	def get_story(self, nr, stories):
		for story in stories:
			if nr == story.number:
				return story
		return False

	def get_parts(self, class_name, story):
		case = class_name.split()

		means_compounds = []
		means_compounds.append(story.means.direct_object.compound)
		ends_compounds = story.ends.compounds

		if story.means.free_form:
			if len(story.means.compounds) > 0:
				if type(story.means.compounds[0]) is list:
					mc = [item for item in sublist for sublist in story.means.compounds]
				else:
					mc = story.means.compounds
				means_compounds.extend(mc)
			
		if len(ends_compounds) > 0:
			if type(ends_compounds[0]) is list:
				ends_compounds = [item for item in sublist for sublist in story.ends.compounds]

		role = []
		means = []
		ends = []
		rme = []

		for token in story.data:
			if token in story.role.text:
				if len(case) != 1:
					role.append(NLPUtility.case(token))
				elif token not in story.role.functional_role.compound:
					role.append(NLPUtility.case(token))
			if token in story.means.text:
				if len(case) != 1:
					means.append(NLPUtility.case(token))
				elif token not in means_compounds:
					means.append(NLPUtility.case(token))
			if story.ends.indicator:
				if token in story.ends.text:
					if len(case) != 1:
						ends.append(NLPUtility.case(token))
					elif token not in ends_compounds:
						ends.append(NLPUtility.case(token))

		if Utility.is_sublist(case, role):
			rme.append('Role')

		if Utility.is_sublist(case, means):
			rme.append('Means')

		if Utility.is_sublist(case, ends):
			rme.append('Ends')

		return rme
			
					

class WeightedToken(object):
	def __init__(self, token, weight):
		self.token = token
		self.case = NLPUtility.case(token)
		self.weight = weight

class WeightAttacher:
	def make(stories, weights):
		weighted_tokens = []
		indices = [weight[0] for weight in weights]
		w = 0.0
		c = ""

		for story in stories:
			if story.has_ends:
				parts = ['role', 'means', 'ends']
			else:
				parts = ['role', 'means']

			for part in parts:
				for token in eval('story.' + str(part) + '.text'):
					c = NLPUtility.case(token)
					if c in indices:
						for weight in weights:
							if weight[0] == c:
								w = weight[1]
								break
					else:
						w = 0.0
					weighted_tokens.append(WeightedToken(token, w))

		return weighted_tokens

class PatternFactory:
	def __init__(self, onto, prolog, weighted_tokens):
		self.onto = onto
		self.prolog = prolog
		self.weighted_tokens = weighted_tokens

	def make_patterns(self, user_stories, threshold):
		pi = PatternIdentifier(self.weighted_tokens)

		for story in user_stories:
			pi.identify(story)
		
		relationships = self.apply_threshold(pi.relationships, threshold)	
		self.create(relationships, user_stories, threshold)

		return self.onto

	def apply_threshold(self, relationships, threshold):
		rel = []

		for r in relationships:
			if self.get_lowest_threshold(r) >= threshold:
				rel.append(r)
		
		return rel

	def get_lowest_threshold(self, relationship):
		wt = self.get_weighted_tokens(relationship)
		lt = 1000.0

		if wt:		
			lt = wt[0].weight
			for w in wt:
				if w.weight < lt:
					lt = w.weight

		return lt

	def get_weighted_tokens(self, relationship):
		wt = []

		if type(relationship[1]) is list:
			wt.extend(relationship[1])
		elif type(relationship[1]) is WeightedToken:
			wt.append(relationship[1])
		if type(relationship[3]) is list:
			wt.extend(relationship[3])
		elif type(relationship[3]) is WeightedToken:
			wt.append(relationship[3])

		return wt

	def create(self, relationships, stories, threshold):
		used = []

		for r in relationships:
			pre = NLPUtility.get_case(r[1])
			post = NLPUtility.get_case(r[3])

			if r[2] != Pattern.parent:
				rel = NLPUtility.get_case(r[4])

			if r[2] == Pattern.parent:
				self.onto.get_class_by_name(r[0], pre, post)
				self.prolog.new_relationship(r[0], pre, 'isa', post)
			elif r[2] == Pattern.subj_dobj:
				self.onto.get_class_by_name(r[0], pre)
				self.onto.get_class_by_name(r[0], post)
				self.make_can_relationship(r[0], pre, rel, post)
				self.prolog.new_relationship(r[0], pre, rel, post)

			self.prolog.get_class_by_name(r[0], pre)
			self.prolog.get_class_by_name(r[0], post)

			used.append(pre)
			used.append(post)

		for wo in self.weighted_tokens:
			if wo.case not in used:
				if wo.weight >= threshold:
					in_stories = self.find_story(wo, stories)
					for in_story in in_stories:
						self.onto.get_class_by_name(in_story, wo.case)

	def make_can_relationship(self, story, pre, rel, post):
		self.make_relationship(story, pre, rel, post, 'can')

	def make_has_relationship(self, story, pre, rel, post):
		self.make_relationship(story, pre, rel, post, 'has')

	def make_relationship(self, story, pre, rel, post, connector):
		self.onto.new_relationship(story, pre, connector + rel, post)	

	def find_story(self, w_token, stories):
		nrs = []
		for story in stories:
			if w_token.case in [NLPUtility.case(t) for t in story.data]:
				nrs.append(story.number)
		return nrs


class PatternIdentifier:
	def __init__(self, weighted_tokens):
		self.weighted_tokens = weighted_tokens
		self.relationships = []
		self.func_role = False

	def identify(self, story):
		self.identify_compound(story)
		self.identify_func_role(story)
		self.identify_subj_dobj(story)
		if story.has_ends:
			self.identify_subj_dobj(story, 'ends')
		self.identify_dobj_conj(story)

		if self.func_role:
			self.relationships.append([-1, 'FunctionalRole', Pattern.parent, 'Person'])

	def identify_compound(self, story):
		compounds = []
		if story.role.functional_role.compound:
			compounds.append(story.role.functional_role.compound)
		if story.means.direct_object.compound:
			compounds.append(story.means.direct_object.compound)
		if story.means.free_form:
			if type(story.means.compounds) is list and len(story.means.compounds) > 0 and type(story.means.compounds[0]) is list:
				compounds.extend(story.means.compounds)
			elif len(story.means.compounds) > 0:
				compounds.append(story.means.compounds)
		if story.ends.free_form:
			if type(story.ends.compounds) is list and len(story.ends.compounds) > 0 and type(story.ends.compounds[0]) is list:
				compounds.extend(story.ends.compounds)
			elif len(story.ends.compounds) > 0:
				compounds.append(story.ends.compounds)

		if compounds:
			for c in compounds:
				self.relationships.append([story.number, [self.getwt(c[0]), self.getwt(c[1])], Pattern.parent, self.getwt(c[1])])

	def identify_func_role(self, story):
		role = []
		has_parent = False

		if story.role.functional_role.compound:
			for c in story.role.functional_role.compound:
				role.append(self.getwt(c))
		else:
			role.append(self.getwt(story.role.functional_role.main))
		
		is_subj = self.is_subject(role)
		
		# Checks if the functional role already has a parent, and then makes this parent the child for 'FunctionalRole'
		if is_subj[0]:
			for i in is_subj[1]:
				if i[1] == Pattern.parent:
					role = i[2]

		self.relationships.append([story.number, role, Pattern.parent, 'FunctionalRole'])
		self.func_role = True			

	def identify_subj_dobj(self, story, part='means'):
		fr = self.get_func_role(story)
			
		if eval('story.' + str(part) + '.main_verb.phrase'):
			mv = eval('story.' + str(part) + '.main_verb.phrase')
		else:
			mv = [eval('story.' + str(part) + '.main_verb.main')]

		if eval('story.' + str(part) + '.direct_object.compound'):
			do = eval('story.' + str(part) + '.direct_object.compound')
		else:
			do = [eval('story.' + str(part) + '.direct_object.main')]
		
		w_fr = [self.getwt(x) for x in fr]
		w_mv = [self.getwt(x) for x in mv]
		w_do = [self.getwt(x) for x in do]

		self.relationships.append([story.number, w_fr, Pattern.subj_dobj, w_do, w_mv])

	def identify_dobj_conj(self, story):
		if story.means.free_form:
			for token in story.means.direct_object.phrase:
				if token.dep_ == 'conj':
					print(token.text, token.dep_, token.head, token.head.dep_, story.text)
				

	def get_func_role(self, story):
		if story.role.functional_role.phrase:
			fr = story.role.functional_role.phrase
		elif story.role.functional_role.compound:
			fr = story.role.functional_role.compound
		else:
			fr = [story.role.functional_role.main]

		return fr

	def is_subject(self, weighted_tokens):
		is_subj = False
		subjects = []

		for r in self.relationships:
			if type(r[1]) is list and type(weighted_tokens) is list:
				case = ""
				case_w = ""
				for i in r[1]:
					case += i.case
				for j in weighted_tokens:
					case_w += j.case
				if i == j:
					subjects.append([r[1], r[2], r[3]])
					is_subj = True														
			if type(r[1]) is str and type(weighted_tokens) is str:
				if r[1] == weighted_tokens:
					subjects.append([r[1], r[2], r[3]])
					is_subj = True					
			if type(r[1]) is WeightedToken and type(weighted_tokens) is WeightedToken:
				if r[1].case == weighted_tokens.case:
					subjects.append([r[1], r[2], r[3]])
					is_subj = True

		return is_subj, subjects	

	def getwt(self, token):
		for wt in self.weighted_tokens:
			if token == wt.token:
				return wt
		self.weighted_tokens.append(WeightedToken(token, 0.0))
		return self.getwt(token)
		

class Pattern(Enum):
	link_to_story = 0
	parent = 1
	subj_dobj = 2
	freeform_conj = 3
