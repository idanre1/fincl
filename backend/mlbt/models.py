# AUTOGENERATED! DO NOT EDIT! File to edit: dev/12_models.ipynb (unless otherwise specified).

__all__ = ['undersample', 'clf_hyper_fit', 'get_model', 'RF_PARAM_GRID', 'XGB_PARAM_GRID', 'LGBM_PARAM_GRID',
           'KNN_PARAM_GRID', 'SVC_PARAM_GRID']

# Cell

import pandas as pd
import numpy as np
import logging
# import tpot

from .utils import PurgedKFold
from math import ceil

from sklearn.model_selection import GridSearchCV, RandomizedSearchCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
from sklearn.dummy import DummyClassifier

from xgboost import XGBClassifier
from lightgbm import LGBMClassifier


def undersample(events, X, y):
    from imblearn.under_sampling import RandomUnderSampler
    under = RandomUnderSampler()

    _, _ = under.fit_sample(X, y)
    X_re = X.iloc[under.sample_indices_].sort_index()
    y_re = y.iloc[under.sample_indices_].sort_index()
    events_re = events.iloc[under.sample_indices_].sort_index()
    return events_re, X_re, y_re


def clf_hyper_fit(
    feat,
    lbl,
    t1,
    pipe_clf,
    param_grid,
    cv=5,
    bagging=[0, None, 1.0],
    rnd_search_iter=0,
    n_jobs=-1,
    pct_embargo=0,
    **fit_params,
):
    if set(lbl.values) == {0, 1}:
        scoring = "f1"  # f1 for meta-labeling
    else:
        scoring = "neg_log_loss"  # symmetric towards all classes

    # 1) hyperparameter searching, on train data
    inner_cv = PurgedKFold(
        n_splits=cv, t1=t1, pct_embargo=pct_embargo, random_state=None
    )
    if rnd_search_iter == 0:
        gs = GridSearchCV(
            estimator=pipe_clf,
            param_grid=param_grid,
            scoring=scoring,
            cv=inner_cv,
            n_jobs=n_jobs,
            iid=False,
        )
    else:
        gs = RandomizedSearchCV(
            estimator=pipe_clf,
            param_distributions=param_grid,
            scoring=scoring,
            cv=inner_cv,
            n_jobs=n_jobs,
            iid=False,
            n_iter=rnd_search_iter,
        )
    gs = gs.fit(feat, lbl, **fit_params)
    return gs


RF_PARAM_GRID = {
    "n_estimators": np.arange(10, 200, 10),
    "max_depth": np.arange(1, 11, 1),
}

XGB_PARAM_GRID = {
    "eta": np.arange(0.2, 0.41, 0.01),
    "max_depth": np.arange(1, 8, 1),
    "colsample_bytree": np.arange(0.3, 1.1, 0.1),
    "gamma": np.arange(0.0, 0.55, 0.05),
    "n_estimators": np.arange(25, 275, 25),
    "min_child_weight": np.arange(1, 10, 1),
}

LGBM_PARAM_GRID = {
    "max_depth": np.arange(1, 8, 1),
    "num_leaves": np.arange(8, 130, 2),
    "colsample_bytree": np.arange(0.3, 1.05, 0.05),
    "n_estimators": np.arange(25, 275, 25),
    "learning_rate": np.arange(0.01, 0.2, 0.01),
}

KNN_PARAM_GRID = {"n_neighbors": np.arange(1, 31, 1), "p": np.arange(1, 4, 1)}

SVC_PARAM_GRID = {
    "C": [0.1, 1, 10, 100, 1000],
    "gamma": [1, 0.1, 0.01, 0.001, 0.0001],
    "probability": [True],
    "max_iter": [100000],
}


def get_model(
    events,
    X_all,
    y_all,
    clf_type,
    optimize_hypers,
    hypers_n_iter,
    num_threads=32,
    n_jobs=4,
    hyper_params=None,
):
    # X_all and y_all in this context are X_train and y_train in the grander scheme
    logging.info(f"Getting model {clf_type}")
    param_grids = {
        "random_forest": RF_PARAM_GRID,
        "xgboost": XGB_PARAM_GRID,
        "lgbm": LGBM_PARAM_GRID,
        "svc": SVC_PARAM_GRID,
        "knn": KNN_PARAM_GRID,
        "dummy": {},
    }
    clfs = {
        "random_forest": RandomForestClassifier,
        "xgboost": XGBClassifier,
        "lgbm": LGBMClassifier,
        "svc": SVC,
        "knn": KNeighborsClassifier,
        "dummy": DummyClassifier,
    }

    hyper_params = hyper_params or {}
    extra_hyper_params = {}

    if clf_type == 'lgbm':
        hypers_n_iter *= 5 # Can afford a bit more since it's fast

    clf = clfs[clf_type](**hyper_params, **extra_hyper_params)

    param_grid = param_grids[clf_type]
    if not param_grid:  # nothing to do
        return clf, hyper_params

    if not hyper_params and optimize_hypers:
        # We generally expect to be run with high num_threads which means we don't have to parallelize at the clf level here
        clf.n_jobs = 1
        logging.info(
            f"hyperparam search n_iter={hypers_n_iter} for {clf_type} on num_threads={num_threads} and n_jobs={clf.n_jobs}"
        )
        events_re, X_re, y_re = undersample(events, X_all, y_all)
        search = clf_hyper_fit(
            feat=X_re,
            lbl=y_re,
            t1=events_re["t1"],
            pipe_clf=clf,
            param_grid=param_grid,
            rnd_search_iter=hypers_n_iter,
            n_jobs=num_threads,
        )

        clf, hyper_params = search.best_estimator_, search.best_params_

    clf.n_jobs = n_jobs
    return clf, hyper_params