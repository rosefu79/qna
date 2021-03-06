from datetime import datetime
from calc import logloss, surround, avgstd
from conf import dataset_name, nb_competences_values, STUDENT_FOLD, QUESTION_FOLD, SHUFFLE_TEST, SINGLE_STUDENT, ONE_SLICE
from my_io import IO, Dataset, say
import numpy as np
import random
import json
import sys

def display(results):
	for name in results:
		print(name, results[name]['mean'])

def nb_mistakes(performance, truth, validation_question_set):
	if not validation_question_set:
		return 0
	return int(sum(round(performance[i]) != truth[i] for i in validation_question_set))  # Beware of np.int64, not JSON serializable

def dummy_count(performance, truth, replied_so_far):
	nb_questions = len(performance)
	# print 'indecision', sum([0.4 <= performance[i] <= 0.6 for i in range(nb_questions) if i not in replied_so_far])
	return sum([(performance[i] < 0.5 and truth[i]) or (performance[i] > 0.5 and not truth[i]) for i in range(nb_questions) if i not in replied_so_far]) # Count errors

def get_results(report, filename, files):
	results = {'dim': report.get('dim', 3)}
	nb_students = len(report['mean_error'])
	budget = len(report['mean_error'][0])
	model_name = report['model_name']
	results[model_name] = {}
	if 'mean_error' in report:
		results[model_name]['mean'] = [avgstd([report['mean_error'][i][t] for i in range(nb_students)]) for t in range(budget)]
	if 'nb_mistakes' in report:
		results[model_name]['count'] = [avgstd([report['nb_mistakes'][i][t] for i in range(nb_students)]) for t in range(budget)]
	if 'delta' in report:
		results[model_name]['delta'] = [avgstd([report['delta'][i][t] for i in range(nb_students)]) for t in range(budget)]
	files.backup('stats-%s-%s-%s' % (dataset_name, filename, datetime.now().strftime('%d%m%Y%H%M%S')), results)

def simulate(model, train_data, test_data, validation_question_set):

	say(datetime.now())
	say('=' * 10, model.name)

	print(len(test_data), 'students to consider')
	nb_students = len(test_data)
	nb_questions = len(test_data[0])
	budget = nb_questions - len(validation_question_set)
	report = {'mean_error': [], 'nb_mistakes': [], 'model_name': model.name, 'dim': model.get_dim()}

	if SHUFFLE_TEST:
		print('Shuffle', len(test_data))
		random.shuffle(test_data)

	for student_id in ([0] if SINGLE_STUDENT else range(nb_students)):
		if student_id % 10 == 0:
			print(student_id)

		say('Étudiant', student_id, list(zip(range(1, nb_questions+1), test_data[student_id])))

		report['mean_error'].append([0] * budget)
		report['nb_mistakes'].append([0] * budget)

		model.init_test(validation_question_set=validation_question_set)
		replied_so_far = []
		results_so_far = []

		say('Estimation initiale :', list(map(lambda x: round(x, 1), model.predict_performance())))
		say('Erreur initiale :', logloss(model.predict_performance(), test_data[student_id]))

		for t in range(1, budget + 1):
			question_id = model.next_item(replied_so_far, results_so_far)

			say('\nRound', t, '-> We ask question', question_id + 1, 'to the examinee.')
			if model.name == 'IRT':
				say('Difficulty:', model.itembank[question_id, :])
			elif model.name == 'QMatrix': 
				say('It requires KC:', map(int, model.Q[question_id]))
			elif model.name == 'MIRT':
				say('It requires KC:', surround(model.V.rx(question_id + 1, True)))

			performance = model.predict_performance()
			# positive_outcome = input('Did you solve it?') == 'y'
			positive_outcome = test_data[student_id][question_id]
			say('Correct!' if positive_outcome else 'Incorrect.') #, "I expected: %f." % round(performance[question_id], 2))

			replied_so_far.append(question_id)
			results_so_far.append(positive_outcome)
			model.estimate_parameters(replied_so_far, results_so_far)
			performance = model.predict_performance()

			say(' '.join(map(lambda x: str(int(10 * round(x, 1))), performance)))
			say('Estimate:', ''.join(map(lambda x: '%d' % int(round(x)), performance)))
			say('   Truth:', ''.join(map(lambda x: '%d' % int(x), test_data[student_id])))
			say('Error computation: ', [performance[i] for i in validation_question_set], [test_data[student_id][i] for i in validation_question_set], logloss(performance, test_data[student_id], validation_question_set))

			report['mean_error'][student_id][t - 1] = logloss(performance, test_data[student_id], validation_question_set)
			report['nb_mistakes'][student_id][t - 1] = nb_mistakes(performance, test_data[student_id], validation_question_set)
			# error_rate[t - 1].append(dummy_count(performance, test_data[student_id], replied_so_far) / (len(performance) - len(replied_so_far)))
			# say('Erreur au tour %d :' % t, error_log[-1][t - 1])
	return report


def main():
	files = IO()
	dataset = Dataset(dataset_name, files)
	dataset.load_subset()
	print(dataset)
	for i_exp in [0] if ONE_SLICE else range(STUDENT_FOLD):
		train_subset = dataset.train_subsets[i_exp]
		test_subset = dataset.test_subsets[i_exp]
		data = np.array(dataset.data)
		for j_exp in [0] if ONE_SLICE else range(QUESTION_FOLD):
			validation_index = set(dataset.validation_question_sets[j_exp])
			files.update(i_exp, j_exp)
			for model in models:
				begin = datetime.now()
				print(begin)
				filename = model.get_prefix() + '-%s-%s' % (dataset.nb_questions, model.get_dim())
				train_data = data[np.ix_(train_subset, dataset.question_subset)]
				test_data = data[np.ix_(test_subset, dataset.question_subset)]
				print(type(model))
				try:
					model.r_data = model.prepare_data(train_data)
				except:
					print('has no rpy interface')
					pass
				# Training
				model.training_step(train_data)
				p = model.compute_all_predictions()
				model.compute_train_test_error(p)
				# Testing
				report = simulate(model, train_data, test_data, validation_index)
				get_results(report, filename, files)
				files.backup('log-%s-%s-%s' % (dataset_name, filename, datetime.now().strftime('%d%m%Y%H%M%S')), report)
				print(datetime.now())


if __name__ == '__main__':
	if sys.argv[1] == 'baseline':
		from baseline import Baseline
		models = [Baseline()]
	elif sys.argv[1] == 'qm':
		from qmatrix import QMatrix
		models = []
		for nb_competences in nb_competences_values:
			models.append(QMatrix(nb_competences=nb_competences))
	elif sys.argv[1] == 'dina':
		from qmatrix import QMatrix
		q = QMatrix()
		q.load('qmatrix-%s' % sys.argv[2])
		# print('test', q.model_error())
		models = [q]
	elif sys.argv[1] == 'qmspe':
		from qmatrix import QMatrix
		q = QMatrix()
		print('Toujours', q.prior)
		q.load('qmatrix-%s' % dataset_name)
		print('Toujours2', q.prior)
		models = [q]
	elif sys.argv[1] == 'irt':
		from irt import IRT
		models = [IRT()]
	elif sys.argv[1] == 'mirt':
		from mirt import MIRT
		models = [MIRT(dim=int(sys.argv[2]))]
	elif sys.argv[1] == 'mirtq':
		from mirt import MIRT
		from qmatrix import QMatrix
		q = QMatrix()
		# q.load('qmatrix-custom')
		q.load('qmatrix-%s' % dataset_name)
		models = [MIRT(q=q)]
	elif sys.argv[1] == 'mirtqspe':
		from mirt import MIRT
		from qmatrix import QMatrix
		q = QMatrix()
		q.load('qmatrix-cdm-new')
		# q.load('qmatrix-cdm')
		models = [MIRT(q=q)]
	elif sys.argv[1] == 'genma':
		from genma import GenMA
		models = [GenMA(dim=int(sys.argv[2]))]
	elif sys.argv[1] == 'mhrm':
		from mhrm import MHRM
		models = [MHRM(dim=2)]
	else:
		from irt import IRT
		models = [IRT(criterion='MEPV')]

	models_names = [model.name for model in models]
	main()
