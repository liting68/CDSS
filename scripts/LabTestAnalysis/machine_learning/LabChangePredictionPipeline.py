#!/usr/bin/python
"""
Pipeline class for managing end to end training, testing,
and analysis of LabChange prediction.
"""

import inspect
import os
import logging

from sys import argv
from pandas import DataFrame, Series
import pandas as pd
import numpy as np
from sklearn.externals import joblib
from sklearn.model_selection import train_test_split

from medinfo.common.Util import log
from medinfo.ml.FeatureSelector import FeatureSelector
from medinfo.dataconversion.FeatureMatrixTransform import FeatureMatrixTransform
from medinfo.dataconversion.FeatureMatrixIO import FeatureMatrixIO
from medinfo.ml.BifurcatedSupervisedClassifier import BifurcatedSupervisedClassifier
from medinfo.ml.SupervisedClassifier import SupervisedClassifier
from medinfo.ml.SupervisedLearningPipeline import SupervisedLearningPipeline
from scripts.LabTestAnalysis.machine_learning.extraction.LabChangeMatrix import LabChangeMatrix

class LabChangePredictionPipeline(SupervisedLearningPipeline):
    def __init__(self, change_params, lab_panel, num_episodes, use_cache=None, random_state=None, build_raw_only=False,):
        SupervisedLearningPipeline.__init__(self, lab_panel, num_episodes, use_cache, random_state)
        self.feat2imputed_dict = {}
        self._change_params = change_params
        self._change_params['feature_old'] = self._lookup_previous_measurement_feature(self._var)
        log.debug('change_params: %s' % self._change_params)

        if build_raw_only:
            self._build_raw_feature_matrix()
            return

        else:
            self._build_raw_feature_matrix()
            self._build_processed_feature_matrix()
            self._train_and_analyze_predictors()

    def _build_model_dump_path(self, algorithm):
        template = '%s' + '-change-%s-model.pkl' % algorithm
        pipeline_file_name = inspect.getfile(inspect.currentframe())
        return SupervisedLearningPipeline._build_model_dump_path(self, template, \
            pipeline_file_name)

    def _build_raw_matrix_path(self):
        template = '%s-change-matrix-%d-episodes-raw.tab'
        pipeline_file_name = inspect.getfile(inspect.currentframe())

        # Build matrix file name.
        slugified_var = '-'.join(self._var.split())
        matrix_name = template % (slugified_var, self._num_rows)

        # Build path using parent class logic for _fetch_data_dir_path.
        # This puts raw matrix in the directory for lab test rather than the
        # subdirectory for the specific change definition.  That way it can be
        # reused in pipelines for multiple different change defs.
        data_dir = SupervisedLearningPipeline._fetch_data_dir_path(self, pipeline_file_name)
        matrix_path = '/'.join([data_dir, matrix_name])

        return matrix_path

    def _build_raw_feature_matrix(self):
        raw_matrix_path = self._build_raw_matrix_path()
        matrix_class = LabChangeMatrix
        SupervisedLearningPipeline._build_raw_feature_matrix(self, matrix_class, \
            raw_matrix_path)

    def _build_processed_matrix_path(self, raw_matrix_path):
        template = '%s-change-matrix-%d-episodes-processed.tab'
        pipeline_file_path = inspect.getfile(inspect.currentframe())
        return SupervisedLearningPipeline._build_matrix_path(self, template, \
            pipeline_file_path)

    def _build_processed_feature_matrix(self):
        # Define parameters for processing steps.
        params = {}
        raw_matrix_path = self._build_raw_matrix_path()
        processed_matrix_path = self._build_processed_matrix_path(raw_matrix_path)

        log.debug('params: %s' % params)

        prev_measurement_feature = self._change_params['feature_old']
        features_to_add = {'change': [self._change_params]}
        features_to_filter_on = [{'feature': prev_measurement_feature,
                                  'value':np.nan}]
        imputation_strategies = {
        }

        features_to_remove = [
            'pat_id', 'order_time', 'order_proc_id', 'ord_num_value',
            'proc_code', 'abnormal_panel', 'all_components_normal',
            'num_normal_components', 'Birth.pre',
            'Male.preTimeDays', 'Female.preTimeDays',
            'RaceWhiteHispanicLatino.preTimeDays',
            'RaceWhiteNonHispanicLatino.preTimeDays',
            'RaceHispanicLatino.preTimeDays',
            'RaceAsian.preTimeDays',
            'RaceBlack.preTimeDays',
            'RacePacificIslander.preTimeDays',
            'RaceNativeAmerican.preTimeDays',
            'RaceOther.preTimeDays',
            'RaceUnknown.preTimeDays',
            'Death.post',
            'Death.postTimeDays',
            'num_components'
        ]
        features_to_keep = [
            # Keep the # of times it's been ordered in past, even if low info.
            '%s.pre' % self._var
        ]
        outcome_label = 'unchanged_yn'
        selection_problem = FeatureSelector.CLASSIFICATION
        selection_algorithm = FeatureSelector.RECURSIVE_ELIMINATION
        percent_features_to_select = 0.05
        matrix_class = LabChangeMatrix
        pipeline_file_path = inspect.getfile(inspect.currentframe())
        data_overview = [
            # Overview:
            'Overview',
            # The outcome label is ___.
            'The outcome label is %s.' % outcome_label,
            # %s is a boolean indicator which summarizes whether the lab test
            '%s is a boolean indicator which summarizes whether the lab test ' % outcome_label,
            # result is unchanged compared to the previous measurement.
            'result is unchanged compared to the previous measurement.',
            # Each row represents a unique lab panel order.
            'Each row represents a unique lab panel order.',
            # Each row contains fields summarizing the patient's demographics,
            "Each row contains fields summarizing the patient's demographics",
            # inpatient admit date, prior vitals, and prior lab results.
            'inpatient admit date, prior vitals, and prior lab results.',
            # Most cells in matrix represent a count statistic for an event's
            "Most cells in matrix represent a count statistic for an event's",
            # occurrence or a difference between an event's time and index_time.
            "occurrence or a difference between an event's time and index_time.",
            # Lab panel orders were only included if a previous measurement of
            "Lab panel orders were only included if a previous measurement of",
            # the same lab panel has been recorded
            "the same lab panel has been recorded."
        ]

        # Bundle parameters into single object
        params['raw_matrix_path'] = raw_matrix_path
        params['processed_matrix_path'] = processed_matrix_path
        params['features_to_add'] = features_to_add
        params['features_to_keep'] = features_to_keep
        params['features_to_filter_on'] = features_to_filter_on
        params['imputation_strategies'] = imputation_strategies
        params['features_to_remove'] = features_to_remove
        params['outcome_label'] = outcome_label
        params['selection_problem'] = selection_problem
        params['selection_algorithm'] = selection_algorithm
        params['percent_features_to_select'] = percent_features_to_select
        params['matrix_class'] = matrix_class
        params['pipeline_file_path'] = pipeline_file_path
        params['data_overview'] = data_overview

        # defer to SupervisedLearningPipeline logic by SX
        fm_io = FeatureMatrixIO()
        log.debug('params: %s' % params)
        # If processed matrix exists, and the client has not requested to flush
        # the cache, just use the matrix that already exists and return.
        processed_matrix_path = params['processed_matrix_path']
        if os.path.exists(processed_matrix_path) and not self._flush_cache:
            # Assume feature selection already happened, but we still need
            # to split the data into training and test data.
            processed_matrix = fm_io.read_file_to_data_frame(processed_matrix_path)
            '''
            Make sure the order of rows is consistent before splitting
            '''
            processed_matrix.sort_index(inplace=True)
            self._train_test_split(processed_matrix, params['outcome_label']) #TODO sxu: when reloading, no pat_id
        else:
            # Read raw matrix.
            raw_matrix = fm_io.read_file_to_data_frame(params['raw_matrix_path'])
            # Initialize FMT.

            # Add outcome label
            raw_fmt = FeatureMatrixTransform()
            raw_fmt.set_input_matrix(raw_matrix)
            self._filter_on_features(raw_fmt, params['features_to_filter_on'])
            self._add_features(raw_fmt, params['features_to_add'])
            raw_matrix = raw_fmt.fetch_matrix()

            # Divide processed_matrix into training and test data.
            # This must happen before feature selection so that we don't
            # accidentally learn information from the test data.

            # TODO: work on this...
            self._train_test_split(raw_matrix, params['outcome_label'])

            fmt = FeatureMatrixTransform()
            train_df = self._X_train.join(self._y_train)
            fmt.set_input_matrix(train_df)

            # Remove features.
            self._remove_features(fmt, params['features_to_remove'])
            # Filter on features
            if 'features_to_filter_on' in params:
                self._filter_on_features(fmt, params['features_to_filter_on'])

            # HACK: When read_csv encounters duplicate columns, it deduplicates
            # them by appending '.1, ..., .N' to the column names.
            # In future versions of pandas, simply pass mangle_dupe_cols=True
            # to read_csv, but not ready as of pandas 0.22.0.
            for feature in raw_matrix.columns.values:
                if feature[-2:] == ".1":
                    fmt.remove_feature(feature)
                    self._removed_features.append(feature)

            # Impute data.
            self._impute_data(fmt, train_df, params['imputation_strategies'])

            # In case any all-null features were created in preprocessing,
            # drop them now so feature selection will work
            fmt.drop_null_features()

            # Build interim matrix.
            train_df = fmt.fetch_matrix()

            self._y_train = pd.DataFrame(train_df.pop(params['outcome_label']))
            self._X_train = train_df

            '''
            Select X_test columns according to processed X_train
            '''
            self._X_test = self._X_test[self._X_train.columns]

            '''
            Impute data according to the same strategy when training
            '''
            for feat in self._X_test.columns:
                self._X_test[feat] = self._X_test[feat].fillna(self.feat2imputed_dict[feat])

            self._select_features(params['selection_problem'],
                params['percent_features_to_select'],
                params['selection_algorithm'],
                params['features_to_keep'])

            train = self._y_train.join(self._X_train)
            test = self._y_test.join(self._X_test)

            processed_matrix = train.append(test)
            '''
            Need to recover the order of rows before writing into disk
            '''
            processed_matrix.sort_index(inplace=True)

            # Write output to new matrix file.
            header = self._build_processed_matrix_header(params)
            fm_io.write_data_frame_to_file(processed_matrix, \
                processed_matrix_path, header)

    def _impute_data(self, fmt, raw_matrix, imputation_strategies):
        for feature in raw_matrix.columns.values:
            if feature in self._removed_features:
                continue
            # If all values are null, just remove the feature.
            # Otherwise, imputation will fail (there's no mean value),
            # and sklearn will ragequit.
            if raw_matrix[feature].isnull().all():
                fmt.remove_feature(feature)
                self._removed_features.append(feature)
            # Only try to impute if some of the values are null.
            elif raw_matrix[feature].isnull().any():
                # If an imputation strategy is specified, follow it.
                if imputation_strategies.get(feature):
                    strategy = imputation_strategies.get(feature)
                    fmt.impute(feature, strategy)
                else:
                    # TODO(sbala): Impute all time features with non-mean value.
                    imputed_value = fmt.impute(feature)
                    self.feat2imputed_dict[feature] = imputed_value
            else:
                '''
                If there is no need to impute, still keep the mean value, in case test data
                need imputation
                TODO sxu: take care of the case of non-mean imputation strategy
                '''
                imputed_value = fmt.impute(feature)
                self.feat2imputed_dict[feature] = imputed_value

    def _fetch_data_dir_path(self, pipeline_module_path):
        # e.g. app_dir = CDSS/scripts/LabTestAnalysis/machine_learning
        app_dir = os.path.dirname(os.path.abspath(pipeline_module_path))

        # e.g. data_dir = CDSS/scripts/LabTestAnalysis/machine_learning/data
        parent_dir_list = app_dir.split('/')
        parent_dir_list.append('data')

        # make subdirectory based on lab test name and change defs
        # e.g. data_dir =  CDSS/scripts/LabTestAnalysis/machine_learning/data/LABCK/change_interval_05
        parent_dir_list.append(self._var)
        paramstr = str(self._change_params['param']).replace('.','')
        change_def = 'change_%s_%s' % (self._change_params['method'], paramstr)
        parent_dir_list.append(change_def)
        data_dir = '/'.join(parent_dir_list)

        # If data_dir does not exist, make it.
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)

        return data_dir

    def _train_and_analyze_predictors(self):
        log.info('Training and analyzing predictors...')
        problem = SupervisedLearningPipeline.CLASSIFICATION
        meta_report = None
        fm_io = FeatureMatrixIO()

        # Build paths for output.
        pipeline_file_name = inspect.getfile(inspect.currentframe())
        data_dir = self._fetch_data_dir_path(pipeline_file_name)

        # Test BifurcatedSupervisedClassifier and SupervisedClassifier.
        algorithms_to_test = list()
        algorithms_to_test.extend(SupervisedClassifier.SUPPORTED_ALGORITHMS)
        for algorithm in SupervisedClassifier.SUPPORTED_ALGORITHMS:
            pass # TODO:(raikens) something in the BifurcatedSupervisedClassifier pipeline is crashing
            #algorithms_to_test.append('bifurcated-%s' % algorithm)
        log.debug('algorithms_to_test: %s' % algorithms_to_test)

        # Train and analyse algorithms.
        for algorithm in algorithms_to_test:
            log.info('Training and analyzing %s...' % algorithm)
            # If report_dir does not exist, make it.
            report_dir = '/'.join([data_dir, algorithm])
            if not os.path.exists(report_dir):
                os.makedirs(report_dir)

            log.debug('report_dir: %s' % report_dir)

            # Define hyperparams.
            hyperparams = {}
            hyperparams['algorithm'] = algorithm
            hyperparams['hyperparam_strategy'] = SupervisedClassifier.EXHAUSTIVE_SEARCH
            hyperparams['max_iter'] = 1024

            # If bifurcated algorithm, define bifurcator.
            if 'bifurcated' in algorithm:
                # bifrucator = LAB.pre == 0
                hyperparams['bifurcator'] = '%s.pre' % self._var
                hyperparams['bifurcation_strategy'] = BifurcatedSupervisedClassifier.EQUAL
                hyperparams['bifurcation_value'] = 0
                hyperparams['bifurcated'] = True

            # Train classifier.
            predictor_path = self._build_model_dump_path(algorithm)
            if os.path.exists(predictor_path) and 'bifurcated' not in algorithm:
                log.debug('Loading model from disk...')
                # TODO(sbala): Fix loblib.load so that it works for bifurcated
                # supervised classifiers.
                self._predictor = joblib.load(predictor_path)
                self._features = self._X_train.columns
                status = SupervisedClassifier.TRAINED
            else:
                status = SupervisedLearningPipeline._train_predictor(self, problem, [0, 1], hyperparams)

            # If failed to train, write an error report.
            y_train_counts = self._y_train[self._y_train.columns[0]].value_counts()
            y_test_counts = self._y_test[self._y_test.columns[0]].value_counts()
            if status == SupervisedClassifier.INSUFFICIENT_SAMPLES:
                # Skip all analysis and reporting.
                # This will be true for all algorithms, so just return.
                # Build error report.
                algorithm_report = DataFrame(
                    {
                    'lab_panel': [self._var],
                    'algorithm': [algorithm],
                    'error': [status],
                    'y_train.value_counts()': [y_train_counts.to_dict()],
                    'y_test.value_counts()': [y_test_counts.to_dict()]
                    },
                    columns=[
                        'lab_panel', 'algorithm', 'error',
                        'y_train.value_counts()', 'y_test.value_counts()'
                    ]
                )
                header = ['LabChangePredictionPipeline("%s", %d)' % (self._var, self._num_rows)]
                # Write error report.
                fm_io.write_data_frame_to_file(algorithm_report, \
                    '/'.join([report_dir, '%s-change-prediction-report.tab' % (self._var)]), \
                    header)
            # If successfully trained, append to a meta report.
            elif status == SupervisedClassifier.TRAINED:
                pipeline_prefix = '%s-change-prediction-%s' % (self._var, algorithm)
                SupervisedLearningPipeline._analyze_predictor(self, report_dir, pipeline_prefix)
                if meta_report is None:
                    meta_report = fm_io.read_file_to_data_frame('/'.join([report_dir, '%s-report.tab' % pipeline_prefix]))
                else:
                    algorithm_report = fm_io.read_file_to_data_frame('/'.join([report_dir, '%s-report.tab' % pipeline_prefix]))
                    log.debug('algorithm_report: %s' % algorithm_report)
                    meta_report = meta_report.append(algorithm_report)
                # Write predictor to disk.
                predictor = SupervisedLearningPipeline.predictor(self)
                predictor_path = self._build_model_dump_path(algorithm)
                joblib.dump(predictor, predictor_path)

        # After building per-algorithm reports, write to meta report.
        # Note that if there were insufficient samples to build any of the
        # algorithms, then meta_report will still be None.
        if meta_report is not None:
            header = ['LabChangePredictionPipeline("%s", %d)' % (self._var, self._num_rows)]
            fm_io.write_data_frame_to_file(meta_report, \
                '/'.join([data_dir, '%s-change-prediction-report.tab' % self._var]), header)

    def _lookup_previous_measurement_feature(self, proc_code):
        # e.g. app_dir = CDSS/scripts/LabTestAnalysis/machine_learning
        pipeline_module_path = inspect.getfile(inspect.currentframe())
        app_dir = os.path.dirname(os.path.abspath(pipeline_module_path))
        with open("%s/LabComponentMap.tab" % app_dir) as map:
            for line in map:
                row = line.split()
                if row[0] == proc_code:
                    return '%s.-14_0.last' % row[1].rstrip()

if __name__ == '__main__':
    log.level = logging.DEBUG
    labs_to_test = [argv[1]]
    change_params = {}
    change_params['method'] = 'sd'
    change_params['feature_new'] = 'ord_num_value'
    params_to_test = [0.5, 0.4, 0.0.2, 0.1]
    sample_size = 12000

    for panel in labs_to_test:
        LabChangePredictionPipeline(change_params, panel, sample_size, use_cache=True, random_state=123456789, build_raw_only=True)
        for param in params_to_test:
            change_params['param'] = param
            LabChangePredictionPipeline(change_params, panel, sample_size, use_cache=True, random_state=123456789)
