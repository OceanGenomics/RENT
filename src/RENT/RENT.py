# -*- coding: utf-8 -*-
"""
Created on Thu Oct  8 11:28:51 2020

@author: ajenul
"""
import matplotlib.pyplot as plt
import numpy as np
import math
import pandas as pd
import seaborn as sns
import sys
import time
import warnings
import hoggorm as ho
import hoggormplot as hopl

from abc import ABC, abstractmethod
from itertools import combinations, combinations_with_replacement
from joblib import Parallel, delayed

from sklearn.linear_model import LogisticRegression, ElasticNet, \
    LinearRegression
from sklearn.metrics import f1_score, precision_score, recall_score, \
                            matthews_corrcoef, r2_score, accuracy_score
from sklearn.model_selection import train_test_split, StratifiedKFold, KFold
from sklearn.preprocessing import PolynomialFeatures, StandardScaler


from scipy.stats import t


class RENT_Base(ABC):
    """
    This is the base class for RENT_Classification and RENT_Regression.
    """

    @abstractmethod
    def validation_study(self, test_data, test_labels, num_drawings,
                          num_permutations):
        pass

    @abstractmethod
    def run_parallel(self, K):
        pass

    @abstractmethod
    def train(self):
        pass

    @abstractmethod
    def par_selection(self, C_params, l1_params, n_splits, testsize_range):
        pass

    @abstractmethod
    def summary_objects(self):
        pass

    def selectFeatures(self, tau_1_cutoff=0.9, tau_2_cutoff=0.9, tau_3_cutoff=0.975):
        """
        Selectes features based on the cutoff values for tau_1_cutoff, tau_2_cutoff and tau_3_cutoff.

        Parameters
        ----------
        tau_1_cutoff : <float>
            Cutoff value for tau_1 criterion. Choose value between 0 and
            1. Default ``tau_1=0.9``.
        tau_2_cutoff : <float>
            Cutoff value for tau_2 criterion. Choose value between 0 and
            1. Default ``tau_2=0.9``.
        tau_3_cutoff : <float>
            Cutoff value for tau_3 criterion. Choose value between 0 and
            1. Default ``tau_3=0.975``.

        Returns
        -------
        <numpy array>
            Array with selected features.

        """
        if not hasattr(self, '_best_C'):
            sys.exit('Run train() first!')

        weight_list = []
        #Loop through all K models
        for K in range(self.K):
            weight_list.append(self.weight_dict[(self._best_C,
                                                 self._best_l1_ratio,
                                                 K)])
        weight_array = np.vstack(weight_list)

        #Compute results based on weights
        counts = np.count_nonzero(weight_array, axis=0)
        self._perc = counts / len(weight_list)
        means = np.mean(weight_array, axis=0)
        stds = np.std(weight_array, axis=0)
        signum = np.apply_along_axis(self.sign_vote, 0, weight_array)
        t_test = t.cdf(
            abs(means / np.sqrt((stds ** 2) / len(weight_list))), \
                (len(weight_list)-1))

        # Conduct a dataframe that stores the results for the criteria
        summary = np.vstack([self._perc, signum, t_test])
        self.summary_df = pd.DataFrame(summary)
        self.summary_df.index = ['tau_1', 'tau_2', 'tau_3']
        self.summary_df.columns = self.feat_names

        self.sel_var = np.where(
                (self.summary_df.iloc[0, :] >= tau_1_cutoff) &
                (self.summary_df.iloc[1, :] >= tau_2_cutoff) &
                (self.summary_df.iloc[2, :] >= tau_3_cutoff\
                            ))[0]
        return self.sel_var

    def summary_criteria(self):
        """
        Summary statistic of the selection criteria tau_1, tau_2 and tau_3
        for each feature.
        
        RETURNS
        -------
        <pandas dataframe>
            Matrix where rows represent selection criteria and columns represent features.
        """
        if not hasattr(self, 'summary_df'):
            sys.exit('Run selectFeatures() first!')
        return self.summary_df

    def plot_selection_frequency(self):
        """
        Plots tau_1 value for each feature.
        """
        if not hasattr(self, '_perc'):
            sys.exit('Run selectFeatures() first!')

        plt.figure(figsize=(10, 7))
        (markers, stemlines, baseline) = plt.stem(self._perc,\
        use_line_collection=True)
        plt.setp(markers, marker='o', markersize=5, color='black',
            markeredgecolor='darkorange', markeredgewidth=0)
        plt.setp(stemlines, color='darkorange', linewidth=0.5)
        plt.show()


    def get_weight_distributions(self, binary = False):
        """
        Feature weights over the ``K`` models (Beta matrix in paper).
        The rows represent weights of one model, columns
        represents weights across models in ensemble for each feature
        
        PARAMETERS
        ----------
            -``binary=True`` : binary matrix where entry is 1 for each
                    weight unequal to 0.
            -``binary=False`` : original weight matrix.

        RETURNS
        -------
        <pandas dataframe>
            Weight matrix.
        """
        if not hasattr(self, 'weight_dict'):
            sys.exit('Run train() first!')

        weights_df = pd.DataFrame()
        for k in self.weight_dict.keys():
            if k[0] == self._best_C and k[1] == self._best_l1_ratio:
                weights_df = weights_df.append( \
                        pd.DataFrame(self.weight_dict[k]))
        weights_df.index = ['mod {0}'.format(x+1) for x in range(self.K)]
        weights_df.columns = self.feat_names
        
        if binary == True:
            return((weights_df != 0).astype(np.int_))
        else:
            return(weights_df)

    def get_scores_list(self):
        """
        Prediction scores over the ``K`` models.

        RETURNS
        -------
        <list>
            Scores list.
        """
        scores_list = []
        for k in self.score_dict.keys():
            if k[0] == self._best_C and k[1] == self._best_l1_ratio:
                scores_list.append(self.score_dict[k])
        return scores_list
    
    def lineplot(self):
        """
        Lineplot of prediction score and % of weights set to 0 over ```K`` models.
        """
        fig, ax = plt.subplots(figsize=(10, 7))
        num_zeroes = np.sum(1 - self.get_weight_distributions(binary=True), \
                            axis=1) / len(self.feat_names)
        
        scores = self.get_scores_list()
        data = pd.DataFrame({"num_zeroes" : num_zeroes, "scores" : scores})
        
        plt.plot(data.num_zeroes.values, linestyle='--', marker='o', \
                 label="% zero weights")
        plt.plot(data.scores.values, linestyle='--', marker='o', label="score")
        plt.legend()
        ax.set_xlabel('ensemble models')
        plt.title("Analysis of ensemble models")
    
    def plot_object_PCA(self, cl=0, comp1=1, comp2=2, 
                        problem='class', hoggorm = True, 
                        hoggorm_plots = [1,2,3,4,6], sel_vars=True):
        """
        PCA analysis. Plots scores, Loadings, Correlation Loadings, Biplot, 
        Explained variance plot

        Parameters
        ----------
        cl : <int>, <str>
            Run PCA on cl. The default is ``0``.
                - ``cl=0``: Class 0.
                - ``cl=1``: Class 1.
                - ``cl='both'``: All objects (incorrect predictions coloring).
                - ``cl='continuous'``: All objects (gradient coloring).
        comp1 : <int>
            First PCA component to plot. The default is 1.
            
        comp2 : <int>
            Second PCA component to plot. The default is 2.
            
        problem : <str>
            Classification or regression problem. The default is 'class'.
                - ``problem='class'``: Classification problem. Can be used with all possible ``cl`` inputs.
                - ``problem='regression'``: Regression problem. Can only be used with ``cl='continuous'``.
        hoggorm : <boolean>
            Plots from hoggormplot package.
        hoggorm_plots : <list>
            Which plots from hoggormplot shall be plotted.
                - 1: scores plot
                - 2: loadings plot
                - 3: correlation loadings plot
                - 4: biplot
                - 5: explained variance plot
        sel_vars : <boolean>
            Only use the features selected with RENT for PCA. The default is True.

        Returns
        -------
        None.

        """
        if cl not in [0, 1, 'both', 'continuous']:
            sys.exit(" 'cl' must be either 0, 1, 'both' or 'continuous'")
        if problem not in ['class', 'regression']:
            sys.exit(" 'problem' must be either 'class' or 'regression' ")
        if not hasattr(self, 'sel_var'):
            sys.exit('Run selectFeatures() first!')
        if not hasattr(self, 'incorrect_labels'):
            sys.exit('Run summary_objects() first!')
        if problem == "regression" and cl != "continuous":
            sys.exit("The input is invalid. For 'problem = regression', 'cl' \
                     must be 'continuous' ")
        # catch if classification with continuous. (check if RENT class or RENT reg)

        if cl != 'continuous':
            dat = pd.merge(self.data, self.incorrect_labels.iloc[:,[1,-1]], \
                                 left_index=True, right_index=True)
            if sel_vars == True:
                variables = list(self.sel_var)
                variables.extend([-2,-1])
        else:
            
            if problem == "regression":
                dat = pd.merge(self.data, self.incorrect_labels.iloc[:,-1], \
                                         left_index=True, right_index=True)
            else:
                obj_mean = pd.DataFrame(np.nanmean( \
                        self.get_object_probabilities(), 1), \
                    index=self.data.index)
                obj_mean.columns = ["pred_means"]
                dat = pd.merge(self.data, obj_mean, \
                                         left_index=True, right_index=True)
            if sel_vars == True:
                variables = list(self.sel_var)
                variables.extend([-1])

        if cl == 'both' or cl == 'continuous':
            if sel_vars == True:
                data = dat.iloc[:,variables]
            else:
                data = dat
        else:
            if sel_vars == True:
                data = dat.iloc[np.where(dat.iloc[:,-2]==cl)[0],variables]
            else:
                data = dat
                
        if cl != 'continuous':
            data = data.sort_values(by='% incorrect')
            pca_model = ho.nipalsPCA(arrX=data.iloc[:,:-2].values, \
                                       Xstand=True, cvType=['loo'])
        else:
            pca_model = ho.nipalsPCA(arrX=data.iloc[:,:-1].values, \
                                       Xstand=True, cvType=['loo'])
        
        scores = pd.DataFrame(pca_model.X_scores())
        scores.index = list(data.index)
        scores.columns = ['PC{0}'.format(x+1) for x in \
                                 range(pca_model.X_scores().shape[1])]
        scores['coloring'] = data.iloc[:,-1]

        XexplVar = pca_model.X_calExplVar()
        var_comp1 = round(XexplVar[comp1-1], 1)
        var_comp2 = round(XexplVar[comp2-1], 1)


        fig, ax = plt.subplots()
        ax.set_xlabel('comp ' + str(comp1) +' ('+str(var_comp1)+'%)', fontsize=10)
        ax.set_ylabel('comp ' + str(comp2) +' ('+str(var_comp2)+'%)', fontsize=10)
        ax.set_title('Scores plot', fontsize=10)
        ax.set_facecolor('silver')

        # Find maximum and minimum scores along the two components
        xMax = max(scores.iloc[:, (comp1-1)])
        xMin = min(scores.iloc[:, (comp1-1)])

        yMax = max(scores.iloc[:, (comp2-1)])
        yMin = min(scores.iloc[:, (comp2-1)])

        # Set limits for lines representing the axes.
        # x-axis
        if abs(xMax) >= abs(xMin):
            extraX = xMax * .4
            limX = xMax * .3

        elif abs(xMax) < abs(xMin):
            extraX = abs(xMin) * .4
            limX = abs(xMin) * .3

        if abs(yMax) >= abs(yMin):
            extraY = yMax * .4
            limY = yMax * .3

        elif abs(yMax) < abs(yMin):
            extraY = abs(yMin) * .4
            limY = abs(yMin) * .3

        xMaxLine = xMax + extraX
        xMinLine = xMin - extraX

        yMaxLine = yMax + extraY
        yMinLine = yMin - extraY

        ax.plot([0, 0], [yMaxLine, yMinLine], color='0.4', linestyle='dashed',
                linewidth=3)
        ax.plot([xMinLine, xMaxLine], [0, 0], color='0.4', linestyle='dashed',
                linewidth=3)

        # Set limits for plot regions.
        xMaxLim = xMax + limX
        xMinLim = xMin - limX

        yMaxLim = yMax + limY
        yMinLim = yMin - limY

        ax.set_xlim(xMinLim, xMaxLim)
        ax.set_ylim(yMinLim, yMaxLim)

        # plot
        if cl == 0:
            plt.scatter(scores['PC'+str(comp1)],
                        scores['PC'+str(comp2)],
                        c= scores['coloring'],
                        cmap='Greens',
                        marker ="^")
            cbar = plt.colorbar()
            cbar.set_label('% incorrect predicted class 0', fontsize=10)
        elif cl == 1:
            plt.scatter(scores['PC'+str(comp1)],
                        scores['PC'+str(comp2)],
                        c= scores['coloring'],
                        cmap='Reds')
            cbar = plt.colorbar()
            cbar.set_label('% incorrect predicted class 1', fontsize=10)
        elif cl == 'both':
            zeroes = np.where(data.iloc[:,-2]==0)[0]
            ones = np.where(data.iloc[:,-2]==1)[0]

            plt.scatter(scores.iloc[zeroes,(comp1-1)],
                        scores.iloc[zeroes,(comp2-1)],
                        c= scores.iloc[zeroes,-1],
                        cmap='Greens',
                        marker="^",
                        # s=120,
                        # edgecolors='none',
                        alpha=0.5)
            cbar = plt.colorbar()
            cbar.ax.tick_params(labelsize=10)
            cbar.set_label('% incorrect predicted class 0', fontsize=10)
            plt.scatter(scores.iloc[ones,(comp1-1)],
                        scores.iloc[ones,(comp2-1)],
                        c= scores.iloc[ones,-1],
                        cmap='Reds',
                        # edgecolors='none',
                        # s=120,
                        alpha=0.5)
            cbar = plt.colorbar()
            cbar.ax.tick_params(labelsize=10)
            cbar.set_label('% incorrect predicted class 1', fontsize=10)

            mlist = []
            col_list = []

            for i in range(len(data.index)):
                if data.iloc[i,-2]==0:
                    mlist.append("^")
                else:
                    mlist.append("o")

            for i in range(len(data.index)):
                if data.iloc[i,-2]==0 and data.iloc[i,-1]==0:
                    col_list.append('honeydew')
                elif data.iloc[i,-2]==1 and data.iloc[i,-1]==0:
                    col_list.append('snow')
                elif data.iloc[i,-2]==0 and data.iloc[i,-1]>0 and data.iloc[i,-1]<50:
                    col_list.append('mediumspringgreen')
                elif data.iloc[i,-2]==1 and data.iloc[i,-1]>0 and data.iloc[i,-1]<50:
                    col_list.append('tomato')
                elif data.iloc[i,-2]==0 and data.iloc[i,-1]>=50 and data.iloc[i,-1]<100:
                    col_list.append('green')
                elif data.iloc[i,-2]==1 and data.iloc[i,-1]>=50 and data.iloc[i,-1]<100:
                    col_list.append('red')
                elif data.iloc[i,-2]==0 and data.iloc[i,-1]==100:
                    col_list.append('darkgreen')
                elif data.iloc[i,-2]==1 and data.iloc[i,-1]==100:
                    col_list.append('maroon')
                else:
                    col_list.append(np.nan)

            for i in range(len(mlist)):
                plt.scatter(scores.iloc[i,(comp1-1)], scores.iloc[i,(comp2-1)],
                            marker=mlist[i], c=col_list[i])

        elif cl == 'continuous':
            plt.scatter(scores.iloc[:,(comp1-1)], scores.iloc[:,(comp2-1)],
                        c=scores.iloc[:,-1],
                        cmap='YlOrRd')
            cbar = plt.colorbar()
            if problem == "class":
                cbar.set_label('average object prediction')
            else:
                cbar.set_label('average absolute error')
        plt.xticks(fontsize=10)
        plt.yticks(fontsize=10)
        objnames = list(data.index.astype('str'))
        if hoggorm == True:
            if cl != 'continuous':
                hopl.plot(pca_model, plots=hoggorm_plots, comp = [comp1,comp2],
                        objNames=objnames, XvarNames=list(data.columns[:-2]))
            else:
                hopl.plot(pca_model, plots=hoggorm_plots, comp = [comp1,comp2],
                        objNames=objnames, XvarNames=list(data.columns[:-1]))
        


    def get_enetParam_matrices(self):
        """
        Three pandas data frames showing result for all combinations
        of ``l1_ratio`` and ``C``.
        
        RETURNS
        -------
        <list> of <pandas dataframes>
            - dataFrame_1: holds average scores for predictive performance
            - dataFrame_2: holds average percentage of how many feature weights were set to zero
            - dataFrame_3: holds harmonic means between dataFrame_1 and dataFrame_2
        """
        if not hasattr(self, 'weight_dict'):
            sys.exit('Run train() first!')
        return self._scores_df, self._zeroes_df, self._combination

    def get_cv_matrices(self):
        """
        Three pandas data frames showing cross-validated result for all combinations
        of ``C`` and ``l1_ratio`` . Only applicable if ``autoEnetParSel=True``.

        RETURNS
        -------
        <list> of <pandas dataframes>
            - dataFrame_1: holds average scores for predictive performance
            - dataFrame_2: holds average percentage of how many feature weights were set to zero
            - dataFrame_3: holds harmonic means between dataFrame_1 and dataFrame_2
        """
        if self.autoEnetParSel == True:
            return self._scores_df_cv, self._zeroes_df_cv, self._combination_cv
        else:
            print("Parameters have not been selected with Cross Validation.")

    def get_enet_params(self):
        """
        Get current hyperparameter combination of ``C`` and ``l1_ratio``, that is used for analyses.
        
        RETURNS
        -------
        <tuple>
            A tuple holding (C, l1_ratio) for the current average predictive performance. This
            combination of C l1_ratio will be used in subsequent class methods.
        """
        if not hasattr(self, '_best_C'):
            sys.exit('Run train() first!')
        return self._best_C, self._best_l1_ratio

    def set_enet_params(self, C, l1):
        """
        Set hyperparameter combination of ``C`` and ``l1_ratio``, that is used for analyses. Only
        useful if ``autoEnetParSel=False``.
        
        PARAMETERS
        ----------
        <float>
            C regularization parameter.
        <float>
            l1 ratio with value in [0,1]. 
        """
        
        if (C not in self.C) | (l1 not in self.l1_ratios):
            sys.exit('autoEnetParSel was True - no weights calculated for this combination')
        self._best_C = C
        self._best_l1_ratio = l1

    def inv(self, num):
        #invert a number except 0
        if num == 0:
            return np.inf
        elif num == np.inf:
            return 0
        else:
            return num ** -1

    def sign_vote(self, arr):
        return np.abs(np.sum(np.sign(arr))) / len(arr)

    def min_max(self, arr):
        return (arr-np.nanmin(arr)) / (np.nanmax(arr)-np.nanmin(arr))

    def get_runtime(self):
        """
        RENT Runtime.
        
        RETURNS
        -------
        <nummeric value>
            Time.
        """
        return self._runtime



class RENT_Classification(RENT_Base):
    """
    This class carries out repeated elastic net feature selection on a given
    binary classification dataset. Feature selection is done on
    multiple train test splits. The user can initiate interactions between
    features that are included in the dataset and as such introduce
    non-linearities.

    PARAMETERS
    -----

    data : <numpy array> or <pandas dataframe>
        Dataset on which feature selection shall be performed.
        Dimension according to the paper: I_train x N

    target : <numpy array> or <pandas dataframe>
        Response variable of data.
        Dimension: I_train x 1 or I_train x 0 when an row-array is used.

    feat_names : <list>
        List holding feature names. Preferably a list of string values.

    C : <list of int or float values>
        List holding regularisation parameters for K models. The lower,
        the stronger the regularization is .

    l1_ratios : <list of int or float values>
        List holding ratios between l1 and l2 penalty. Must be in [0,1]. For
        pure l2 use 0, for pure l1 use 1.

    autoEnetParSel : <boolean>
        Cross validated elastic net hyperparameter selection.
            - ``autoEnetParSel=True`` : peform a cross validation pre-hyperparameter search, s.t. RENT runs only with one hyperparamter setting.
            - ``autoEnetParSel=False`` : perform RENT with each combination of ``C`` and ``l1_ratios``.
        
    poly : <str> 
        Create non-linear features.
            - ``poly='OFF'`` : no feature interaction.
            - ``poly='ON'`` : feature interaction and squared features (2-polynoms).
            - ``poly='ON_only_interactions'`` : only feature interactions, no squared features.

    testsize_range : <tuple float>
         Range of random proportion of dataset toinclude in test set,
         low and high are floats between 0 and 1, default (0.2, 0.6).
         Testsize can be fixed by setting low and high to the same value.

    scoring : <str>
        The metric to evaluate K models. Default: ``metric='mcc'``.
            - ``scoring='accuracy'`` :  Accuracy
            - ``scoring='f1'`` : F1-score
            - ``scoring='precision'`` : Precision
            - ``scoring='recall'``: Recall
            - ``scoring='mcc'`` : Matthews Correlation Coefficient

    classifier : <str>
        Classifier used in RENT.
            -``classifier='logreg'`` : Logistic Regression

    K : <int>
        Number of unique train-test splits. Default: ``K=100``.

    scale : <boolean>
        Scale each of the K train datasets. Default: ``scale=True``.
    
    random_state : <None or int>
        Set a random state to reproduce your results. Default: ``random_state=None``.
        - ``random_state=None`` : no random seed. 
        - ``random_state={0,1,2,...}`` : random seed set.
        
    verbose : <int>
        Track the train process if value > 1. If ``value = 1``, only the overview
        of RENT input will be shown.

    RETURNS
    ------
    <class>
        A class that contains the RENT-Regression model.
    """

    def __init__(self, data, target, feat_names=[], C=[1,10], l1_ratios = [0.6],
                 autoEnetParSel=True, poly='OFF',
                 testsize_range=(0.2, 0.6), scoring='accuracy',
                 classifier='logreg', K=100, scale = True, random_state = None, 
                 verbose = 0):

        if any(c < 0 for c in C):
            sys.exit('C values must not be negative!')
        if any(l < 0 for l in l1_ratios) or any(l > 1 for l in l1_ratios):
            sys.exit('l1 ratios must be in [0,1]!')
        if autoEnetParSel not in [True, False]:
            sys.exit('autoEnetParSel must be True or False!')
        if scale not in [True, False]:
            sys.exit('scale must be True or False!')
        if poly not in ['ON', 'ON_only_interactions', 'OFF']:
            sys.exit('Invalid poly parameter!')
        # for testsize range criteria should be added.
        if scoring not in ['accuracy', 'f1', 'mcc']:
            sys.exit('Invalid scoring!')
        if classifier not in ['logreg', 'linSVC']:
            sys.exit('Invalid classifier')
        if K<=0:
            sys.exit('Invalid K!')
        if K<10:
            # does not show warning...
            warnings.warn('Attention: K is very small!', DeprecationWarning)
        if len(target.shape) == 2 :
            target = target.values


        # Print parameters for checking if verbose = True
        if verbose == 1:
            print('data dimension:', np.shape(data), ' data type:', type(data))
            print('target dimension', np.shape(target))
            print('regularization parameters C:', C)
            print('elastic net l1_ratios:', l1_ratios)
            print('number of models in ensemble:', K)
            print('scale:', scale)
            print('classifier:', classifier)
            print('random state:', random_state)
            print('verbose:', verbose)


        # Define all objects needed later in methods below
        self.target = target
        self.K = K
        self.feat_names = feat_names
        self.scoring = scoring
        self.classifier = classifier
        self.testsize_range = testsize_range
        self.scale = scale
        self.verbose = verbose
        self.autoEnetParSel = autoEnetParSel
        self.random_state = random_state


        # Check if data is dataframe and add index information
        if isinstance(data, pd.DataFrame):
            if isinstance(data.index, list):
                self.indices = data.index
            else:
                data.index = list(data.index)
                self.indices = data.index
        else:
            self.indices = list(range(data.shape[0]))

        if isinstance(self.target, pd.Series):
            self.target.index = data.index



        # If no feature names are given, create some
        if len(self.feat_names) == 0:
            print('No feature names found - automatic generate feature names.')

            for ind in range(1, np.shape(data)[1] + 1):
                self.feat_names.append('f' + str(ind))


        # Extend data if poly was set to 'ON' or 'ON_only_interactions'
        if poly == 'ON':
            polynom = PolynomialFeatures(interaction_only=False, \
                                         include_bias=False)
            self.data = polynom.fit_transform(data)
            polynom_comb = list(combinations_with_replacement(self.feat_names,\
                                                              2))
            polynom_feat_names = []
            # Construct a new name for squares and interactions
            for item in polynom_comb:
                if item[0] == item[1]:
                    name = item[0] + '^2'
                else:
                    name = item[0] + '*' + item[1]
                polynom_feat_names.append(name)

            flist = list(self.feat_names)
            flist.extend(polynom_feat_names)
            self.feat_names = flist
            self.data = pd.DataFrame(self.data)
            self.data.index = self.indices
            self.data.columns = self.feat_names

        elif poly == 'ON_only_interactions':
            polynom = PolynomialFeatures(interaction_only=True,\
                                         include_bias=False)
            self.data = polynom.fit_transform(data)

            polynom_comb = list(combinations(self.feat_names, 2))
            polynom_feat_names = []

            # Construct a new name for squares and interactions
            for item in polynom_comb:
                name = item[0] + '*' + item[1]
                polynom_feat_names.append(name)

            flist = list(self.feat_names)
            flist.extend(polynom_feat_names)
            self.feat_names = flist
            self.data = pd.DataFrame(self.data)
            self.data.index = self.indices
            self.data.columns = self.feat_names

        elif poly == 'OFF':
            self.data = pd.DataFrame(data)
            self.data.index=self.indices
            self.data.columns = self.feat_names

        else:
            sys.exit('Value for paramter "poly" not regcognised.')

        if self.autoEnetParSel == True:
            self.C, self.l1_ratios = self.par_selection(C=C, l1_ratios=l1_ratios)
            self.C = [self.C]
            self.l1_ratios = [self.l1_ratios]
        else:
            self.C = C
            self.l1_ratios = l1_ratios

    def run_parallel(self, K):
        """
        Parallel computation of ``K`` * ``len(C)`` * ``len(l1_ratios)`` models.

        PARAMETERS
        -----
        ``K`` : range of train-test splits
        """

        # Loop through all C
        for C in self.C:
            for l1 in self.l1_ratios:
                
                if self.random_state == None:
                    X_train, X_test, y_train, y_test = train_test_split(
                          self.data, self.target,
                          test_size=self.random_testsizes[K],
                          stratify=self.target, random_state=None)
                else:
                    X_train, X_test, y_train, y_test = train_test_split(
                          self.data, self.target,
                          test_size=self.random_testsizes[K],
                          stratify=self.target, random_state=K)

#                self.train_sets.append(X_train)
                self.X_test = X_test

                # Initialise standard scaler and compute mean and STD from
                # training data.
                # Transform train and test dataset
                if self.scale == True:
                    sc = StandardScaler()
                    sc.fit(X_train)
                    X_train_std = sc.transform(X_train)
                    X_test_std = sc.transform(X_test)
                elif self.scale == False:
                    X_train_std = X_train.copy().values
                    X_test_std = X_test.copy().values

                if self.verbose > 1:
                    print('C = ', C, 'l1 = ', l1, ', TT split = ', K)

                if self.classifier == 'logreg':
                    # Trian a logistic regreission model
                    model = LogisticRegression(solver='saga',
                                            C=C,
                                            penalty='elasticnet',
                                            l1_ratio=l1,
                                            n_jobs=-1,
                                            max_iter=5000,
                                            random_state=self.random_state).\
                                            fit(X_train_std, y_train)

                # elif self.classifier == 'linSVC':
                #     model = LinearSVC(penalty='l1',
                #                     C=C,
                #                     dual=False,
                #                     max_iter=8000,
                #                     random_state=0).\
                #                     fit(X_train_std, y_train)
                else:
                    sys.exit('No valid classifier.')

                # Get all weights (coefficients). Those that were selected
                # are non-zero, otherwise zero
                #print(logreg.coef_)
                self.weight_dict[(C, l1, K)] = model.coef_
                self.weight_list.append(model.coef_)

                if self.scoring == 'accuracy':
                    y_test_pred = model.predict(X_test_std)
                    score = model.score(X_test_std, y_test)
                elif self.scoring == 'f1':
                    y_test_pred = model.predict(X_test_std)
                    score = f1_score(y_test, y_test_pred)
                elif self.scoring == 'precision':
                    y_test_pred = model.predict(X_test_std)
                    score = precision_score(y_test, y_test_pred)
                elif self.scoring == 'recall':
                    y_test_pred = model.predict(X_test_std)
                    score = recall_score(y_test, y_test_pred)
                elif self.scoring == 'mcc':
                    y_test_pred = model.predict(X_test_std)
                    score = matthews_corrcoef(y_test, y_test_pred)

                #check if we need score_all and score_dict
                self.score_dict[(C, l1, K)] = score
                self.score_list.append(score)

                # Collect true values and predictions in dictionary

                predictions = pd.DataFrame({'y_test':y_test, \
                                       'y_pred': y_test_pred})
                predictions.index = X_test.index

                # calculate predict_proba for current train/test and weight
                # initialization
                self.predictions_dict[(C, l1, K)] = predictions
                if(self.classifier == 'logreg'):
                    self.probas[(C, l1, K)] = pd.DataFrame( \
                           model.predict_proba(X_test_std), index = \
                                X_test.index)

    def train(self):
        """
        This method trains ``K`` * ``len(C)`` * ``len(l1_ratios)`` models in total. The number
        of models using the same hyperparamters is ``K``.
        For each model elastic net regularisation is applied for variable selection. Internally
        train calls the ``run_parallel()`` function.
        """
        #check if this is needed and does what it should (probably doesn't work because of parallelization)
        # np.random.seed(0)
        self.random_testsizes = np.random.uniform(self.testsize_range[0],
                                                  self.testsize_range[1],
                                                  self.K)

        # Initiate a dictionary holding coefficients for each model. Keys are
        # (C, K, num_w_init)
        self.weight_dict = {}

        # Initiate a dictionary holding computed performance metric for each
        self.score_dict = {}


        # Collect all coefs in a list that will be converted to a numpy array
        self.weight_list = []

        # Collect all coefs in a list that will be converted to a numpy array
        self.score_list = []

        # Initialize a dictionary to predict incorrect labels
        self.predictions_dict = {}

        # store
        self.probas = {}
        self.pred_proba_dict = {}

        # stop runtime
        start = time.time()
        # Call parallelization function
        Parallel(n_jobs=-1, verbose=0, backend='threading')(
             map(delayed(self.run_parallel), range(self.K)))
        ende = time.time()
        self._runtime =  ende - start #'{:5.3f}s'.format(ende-start)

        # Build a dictionary with the prediction probabilities
        for C in self.C:
            for l1 in self.l1_ratios:
                count =  0
                vec = pd.DataFrame(np.nan, index= self.indices, \
                                   columns = ['remove'])
                for k in self.probas.keys():

                    if k[0] == C and k[1] == l1:
                        vec.loc[self.probas[k].index,count] = \
                        self.probas[k].iloc[:, 1].values
                        count += 1

                vec = vec.iloc[:, 1:]

                self.pred_proba_dict[(C, l1)] = vec


        # find best parameter setting and matrices
        result_list=[]
        for l1 in self.l1_ratios:
            for C in self.C:
                spec_result_list = []
                for k in self.score_dict.keys():
                    if k[0] == C and k[1] ==l1:
                        spec_result_list.append(self.score_dict[k])
                result_list.append(spec_result_list)

        means=[]
        for r in range(len(result_list)):
            means.append(np.mean(result_list[r]))

        self._scores_df = pd.DataFrame(np.array(means).reshape(\
                                  len(self.l1_ratios), \
                                  len(self.C)), \
        index= self.l1_ratios, columns = self.C)

        self._zeroes_df = pd.DataFrame(index = self.l1_ratios,\
                                   columns=self.C)
        for l1 in self.l1_ratios:
            for C in self.C:
                count = 0
                for K in range(self.K):
                    nz = \
                    len(np.where(pd.DataFrame(self.weight_dict[(C, l1, K)\
])==0)[0])
                    count = count + nz / len(self.feat_names)
                count = count / (self.K)
                self._zeroes_df.loc[l1, C] = count

        if len(self.C)>1 or len(self.l1_ratios)>1:
            normed_scores = pd.DataFrame(self.min_max(self._scores_df))
            normed_zeroes = pd.DataFrame(self.min_max(self._zeroes_df))
            normed_zeroes = normed_zeroes.astype('float')

            self._combination = 2 * ((normed_scores.copy().applymap(self.inv) + \
                                        normed_zeroes.copy().applymap(
                                            self.inv)).applymap(self.inv))
        else:
            self._combination = 2 * ((self._scores_df.copy().applymap(self.inv) + \
                                 self._zeroes_df.copy().applymap(
                                     self.inv)).applymap(self.inv))
        self._combination.index = self._scores_df.index.copy()
        self._combination.columns = self._scores_df.columns.copy()

        self._scores_df.columns.name = 'Scores'
        self._zeroes_df.columns.name = 'Zeroes'
        self._combination.columns.name = 'Harmonic Mean'

        best_row, best_col  = np.where(
            self._combination == np.nanmax(self._combination.values))
        self._best_l1_ratio = self._combination.index[np.nanmax(best_row)]
        self._best_C = self._combination.columns[np.nanmin(best_col)]

    def par_selection(self,
                        C,
                        l1_ratios,
                        n_splits=5,
                        testsize_range=(0.25,0.25)):
        """
        Preselect best `C` and `l1 ratio` with Cross Validation.

        PARAMETERS
        ----------
        C: <list of int or float values>
            List holding regularisation parameters for `K` models. The lower, the
            stronger the regularization is.

        l1_ratios: <list of int or float values>
            List holding ratios between l1 and l2 penalty. Must be in [0,1]. For
            pure l2 use 0, for pure l1 use 1.
        n_splits : <int>
            Number of cross validation folds. Default ``n_splits=5``.
            
        testsize_range: <tuple float>
            Range of random proportion of dataset toinclude in test set,
            low and high are floats between 0 and 1. Default ``testsize_range=(0.2, 0.6)``.
            Testsize can be fixed by setting low and high to the same value.

        RETURNS
        -------
        <tuple>
            - First entry: suggested `C` parameter.
            - Second entry: suggested `l1 ratio`.

        """

        skf = StratifiedKFold(n_splits=n_splits, random_state=self.random_state,\
                              shuffle=True)

        scores_df = pd.DataFrame(np.zeros, index=l1_ratios, columns=C)
        zeroes_df = pd.DataFrame(np.zeros, index=l1_ratios, columns=C)


        def run_parallel(l1):
            """
            Parallel computation of for ``K`` * ``C`` * ``l1_ratios`` models.

            PARAMETERS
            -----
            l1: current l1 ratio in the parallelization framework.
            """
            for reg in C:
                scores = list()
                zeroes = list()
                for train, test in skf.split(self.data, self.target):
                    if self.scale == True:
                        sc = StandardScaler()
                        train_data = sc.fit_transform(self.data.iloc[train, :])
                        train_target = self.target[train]
                        test_data_split = sc.transform(self.data.iloc[test, :])
                        test_target = self.target[test]
                    elif self.scale == False:
                        train_data = self.data.iloc[train, :].values
                        train_target = self.target[train]
                        test_data_split = self.data.iloc[test, :].values
                        test_target = self.target[test]

                    sgd = LogisticRegression(penalty="elasticnet", C=reg,
                                             solver="saga", l1_ratio=l1,
                                             random_state=self.random_state)
                    sgd.fit(train_data, train_target)

                    params = np.where(sgd.coef_ != 0)[1]

                    if len(params) == 0:
                        scores.append(np.nan)
                        zeroes.append(np.nan)
                    else:
                        zeroes.append((len(self.data.columns)-len(params))\
                                      /len(self.data.columns))


                        train_data_1 = train_data[:,params]
                        test_data_1 = test_data_split[:, params]


                        model = LogisticRegression(penalty='none',
                                                   max_iter=8000,
                                                   solver="saga",
                                                   random_state=self.random_state).\
                                fit(train_data_1, train_target)
                        scores.append(matthews_corrcoef(test_target, \
                                        model.predict(test_data_1)))

                scores_df.loc[l1, reg] = np.nanmean(scores)
                zeroes_df.loc[l1, reg] = np.nanmean(zeroes)

        self._scores_df_cv = scores_df
        self._zeroes_df_cv = zeroes_df
        self._scores_df_cv.columns.name = 'Scores'
        self._zeroes_df_cv.columns.name = 'Zeroes'

        Parallel(n_jobs=-1, verbose=0, backend="threading")(
             map(delayed(run_parallel), l1_ratios))

        if len(np.unique(scores_df.values)) ==1:
            best_row, best_col = np.where(zeroes_df.values == \
                                                  np.nanmax(zeroes_df.values))
            best_l1 = zeroes_df.index[np.nanmax(best_row)]
            best_C = zeroes_df.columns[np.nanmin(best_col)]

        else:
            normed_scores = pd.DataFrame(self.min_max(scores_df.copy().values))
            normed_zeroes = pd.DataFrame(self.min_max(zeroes_df.copy().values))

            combination = 2 * ((normed_scores.copy().applymap(self.inv) + \
                           normed_zeroes.copy().applymap(self.inv)
                           ).applymap(self.inv))

            combination.index = scores_df.index.copy()
            combination.columns = scores_df.columns.copy()
            best_combination_row, best_combination_col = np.where(combination == \
                                                      np.nanmax(combination.values))
            best_l1 = combination.index[np.nanmax(best_combination_row)]
            best_C = combination.columns[np.nanmin(best_combination_col)]

        self._combination_cv = combination
        self._combination_cv.columns.name = 'Harmonic Mean'

        return(best_C, best_l1)


    def summary_objects(self):
        """
        This method computes a summary of classifications for each sample
        across all models, where the sample was part of the test set.
        Contains information on how often a sample has been mis-classfied.

        RETURNS
        -------
        <pandas dataframe>
        Data matrix. Rows represent objects, columns represent generated variables.

        """
        if not hasattr(self, '_best_C'):
            sys.exit('Run train() first!')

        self.incorrect_labels = pd.DataFrame({'# test':np.repeat\
                                      (0, np.shape(self.data)[0]),
                                      'class':self.target,
                                      '# incorrect':np.repeat\
                                      (0, np.shape(self.data)[0])})
        self.incorrect_labels.index=self.indices.copy()

        specific_predictions = []
        for K in range(self.K):
            specific_predictions.append(
                self.predictions_dict[(self._best_C, self._best_l1_ratio, K)])
        for dataframe in range(len(specific_predictions)):
            for count, tup in enumerate(
                    zip(specific_predictions[dataframe].y_test, \
                        specific_predictions[dataframe].y_pred)):
                ind = specific_predictions[dataframe].index[count]

                # Upgrade ind by one if used as test object
                self.incorrect_labels.loc[ind,'# test'] += 1
                if tup[0] != tup[1]:
                    # Upgrade number of incorrectly classified
                    self.incorrect_labels.loc[ind,'# incorrect'] += 1

        self.incorrect_labels['% incorrect'] = \
        (self.incorrect_labels["# incorrect"] \
             / self.incorrect_labels['# test']) * 100

        return self.incorrect_labels


    def get_object_probabilities(self):
        """
        Logistic Regression probabilities for each object.

        RETURNS
        -------
        <pandas dataframe>
        Matrix, where rows represent objects and columns represent logistic regression 
            probability outputs (probability of belonging to class 1).

        """

        if not hasattr(self, 'pred_proba_dict'):
            sys.exit('Run train() first!')

        # predicted probabilities only if Logreg
        if self.classifier != 'logreg':
            return warnings.warn('Classifier must be "logreg"!')
        else:
            self.pp_data = self.pred_proba_dict[
                (self._best_C, self._best_l1_ratio)].copy()

            self.pp_data.columns = ['mod {0}'.format(x+1) \
                                        for x in range(
                                                self.pp_data.shape[1])]
            return self.pp_data

    def plot_object_probabilities(self, object_id, binning='auto', lower=0,
                                  upper=1, kde=False, norm_hist=False):
        """
        Histograms of predicted probabilities.
        
        PARAMETERS
        ----------
        object_id : <list of int or str>
            Samples/Objects whos histograms shall be plotted.     
        lower : <float>
            Lower bound of the x-axis. Default ``lower=0``.
        upper : <float>
            Upper bound of the x-axis. Default ``upper=1``.
        kde : <boolean>
            Kernel density estimation, from `seaborn distplot`.
            Default: ``kde=False``.
        norm_hist : <boolean>
            Normalize the histogram, from `seaborn distplot`.
            Default: ``norm_hist=False``.              
        """
        
        if not hasattr(self, '_best_C'):
            sys.exit('Run train() first!')
            
        target_objects = pd.DataFrame(self.target)
        target_objects.index = self.pred_proba_dict[self._best_C, \
                              self._best_l1_ratio].index
        self.t = target_objects
        for obj in object_id:
            fig, ax = plt.subplots()
            data = self.pred_proba_dict[self._best_C, \
                              self._best_l1_ratio].loc[obj,:].dropna()

            if binning == "auto":
                bins = None
            if binning == "rice":
                bins = math.ceil(2 * len(data) ** (1./3.))
            if binning == "sturges":
                bins = math.ceil(math.log(len(data), 2)) + 1

            sns.set(font_scale=0.5)
            sns.set_style("white")
            ax=sns.distplot(data,
                            bins=bins,
                            color = 'darkblue',
                            hist_kws={'edgecolor':'darkblue'},
                            kde_kws={'linewidth': 3},
                            kde=kde,
                            norm_hist=norm_hist)
            ax.set(xlim=(lower, upper))
            ax.axvline(x=0.5, color='k', linestyle='--', label ="Threshold")
            ax.legend(fontsize=10)

            if norm_hist == False:
                ax.set_ylabel('absolute frequencies', fontsize=10)
                ax.set_xlabel('ProbC1', fontsize=10)
            else:
                ax.set_ylabel('frequencies')
                ax.set_xlabel('ProbC1')
            ax.set_title('Object: {0}, True class: {1}'.format(obj, \
                         target_objects.loc[obj,:].values[0]), fontsize=10)



    def validation_study(self, test_data, test_labels, num_drawings, num_permutations,
                          metric='mcc', alpha=0.05):
        """
        Two validation studies based on a statistical `t`-test. The null-hypotheses claims that
            -RENT is not better than random feature selection.
            -RENT performs equally on the real and a randomly permutated target.

        PARAMETERS
        ----------
        test_data : <numpy array> or <pandas dataframe>
            Dataset, used to evalute Logistic Models in the validation study.
            Dimension according to the paper: I_test x N
        test_lables: <numpy array> or <pandas dataframe>
            Response variable of the dataset.
            Dimension: I_train x 1 or I_train x 0 when an row-array is used.
        num_drawings: <int>
            Number of independent feature subset drawings for VS1, more information given in the paper.
        num_permutations: <int>
            Number of independent test_labels permutations for VS2, more information given in the paper.
        metric: <str>
            The metric to evaluate ``K`` models. Default: ``metric='mcc'``.
                - ``scoring='accuracy'`` :  Accuracy
                - ``scoring='f1'`` : F1-score
                - ``scoring='precision'`` : Precision
                - ``scoring='recall'``: Recall
                - ``scoring='mcc'`` : Matthews Correlation Coefficient

        alpha: <float>
            Significance level for the `t`-test. Default ``alpha=0.05``.
        """
        if not hasattr(self, 'sel_var'):
            sys.exit('Run selectFeatures() first!')

        # RENT prediction
        if self.scale == True:
            sc = StandardScaler()
            train_RENT = sc.fit_transform(self.data.iloc[:, self.sel_var])
            test_RENT = sc.transform(test_data.iloc[:, self.sel_var])
        elif self.scale == False:
            train_RENT = self.data.iloc[:, self.sel_var].values
            test_RENT = test_data.iloc[:, self.sel_var].values
        if self.classifier == 'logreg':
                model = LogisticRegression(penalty='none', max_iter=8000,
                                           solver="saga", \
                                           random_state=self.random_state).\
                    fit(train_RENT,self.target)
        else:
            print("something")

        if metric == 'mcc':
                score = matthews_corrcoef(test_labels, model.predict(test_RENT))
        elif metric == 'f1':
            score = f1_score(test_labels, model.predict(test_RENT))
        elif metric == 'acc':
            score = accuracy_score(test_labels, model.predict(test_RENT))

        # VS1
        VS1 = []
        for K in range(num_drawings):
            # Randomly select features (# features = # RENT features selected)
            columns = np.random.RandomState(seed=K).choice(
                range(0,len(self.data.columns)),
                                    len(self.sel_var))
            if self.scale == True:
                sc = StandardScaler()
                train_VS1 = sc.fit_transform(self.data.iloc[:, columns])
                test_VS1 = sc.transform(test_data.iloc[:, columns])
            elif self.scale == False:
                train_VS1 = self.data.iloc[:, columns].values
                test_VS1 = test_data.iloc[:, columns].values
            if self.classifier == 'logreg':
                model = LogisticRegression(penalty='none', max_iter=8000,
                                           solver="saga", 
                                           random_state=self.random_state).\
                    fit(train_VS1,self.target)
            else:
                print("something")
            if metric == 'mcc':
                VS1.append(matthews_corrcoef(test_labels, \
                                                    model.predict(test_VS1)))
            elif metric == 'f1':
                VS1.append(f1_score(test_labels, \
                                                    model.predict(test_VS1)))
            elif metric == 'acc':
                VS1.append(accuracy_score(test_labels, \
                                                    model.predict(test_VS1)))

        #p_value_VS1 = sum(VS1 > score) / len(VS1)
        T = (np.mean(VS1) - score) / (np.std(VS1,ddof=1) / np.sqrt(len(VS1)))
        print("mean VS1", np.mean(VS1))
        p_value_VS1 = t.cdf(T, len(VS1)-1)
        print("VS1: p-value for average score from random feature drawing: ", p_value_VS1)

        if p_value_VS1 <= alpha:
            print('With a significancelevel of ', alpha, ' H0 is rejected.')
        else:
            print('With a significancelevel of ', alpha, ' H0 is accepted.')
        print(' ')
        print('-----------------------------------------------------------')
        print(' ')
        # VS2
        sc = StandardScaler()
        test_data.columns = self.data.columns
        VS2 = []
        if self.scale == True:
            train_VS2 = sc.fit_transform(self.data.iloc[:,self.sel_var])
            test_VS2 = sc.transform(test_data.iloc[:, self.sel_var])
        elif self.scale == False:
            train_VS2 = self.data.iloc[:,self.sel_var].values
            test_VS2 = test_data.iloc[:, self.sel_var].values
        if self.classifier == 'logreg':
            model = LogisticRegression(penalty='none', max_iter=8000,
                                       solver="saga", 
                                       random_state=self.random_state ).\
                    fit(train_VS2, self.target)
        else:
            print("add model")

        for K in range(num_permutations):
            if metric == 'mcc':
                VS2.append(matthews_corrcoef(
                        np.random.RandomState(seed=K).permutation(test_labels),\
                        model.predict(test_VS2)))
            elif metric == 'f1':
                VS2.append(f1_score(
                        np.random.RandomState(seed=K).permutation(test_labels),\
                        model.predict(test_VS2)))
            elif metric == 'acc':
                VS2.append(accuracy_score(
                        np.random.RandomState(seed=K).permutation(test_labels),\
                        model.predict(test_VS2)))


        # p_value_VS2 = sum(VS2 > score) / len(VS2)
        print("Mean VS2", np.mean(VS2))
        T = (np.mean(VS2) - score) / (np.std(VS2,ddof=1) / np.sqrt(len(VS2)))
        p_value_VS2 = t.cdf(T, len(VS2)-1)
        print("VS2: p-value for score from permutation of test labels: ", p_value_VS2)

        if p_value_VS2 <= alpha:
            print('With a significancelevel of ', alpha, ' H0 is rejected.')
        else:
            print('With a significancelevel of ', alpha, ' H0 is accepted.')

        plt.figure(figsize=(15, 7))
        sns.kdeplot(VS1, shade=True, color="b", label='VS1')
        sns.kdeplot(VS2, shade=True, color="g", label='VS2')
        plt.axvline(x=score, color='r', linestyle='--',
                    label='RENT prediction score')
        plt.legend(prop={'size': 12})
        plt.ylabel('density', fontsize=14)
        plt.xticks(fontsize=12)
        plt.yticks(fontsize=12)
        plt.title('validation Study', fontsize=18)

class RENT_Regression(RENT_Base):
    """
    This class carries out repeated elastic net feature selection on a given
    regressionn dataset. Feature selection is done on
    multiple train test splits. The user can initiate interactions between
    features that are included in the dataset and as such introduce
    non-linearities.

    PARAMETERS
    -----

    data: <numpy array> or <pandas dataframe>
        Dataset on which feature selection shall be performed.
        Dimension according to the paper: I_train x N

    target: <numpy array> or <pandas dataframe>
        Response variable of data.
        Dimension: I_train x 1 or I_train x 0 when an row-array is used.

    feat_names : <list>
        List holding feature names. Preferably a list of string values.'
    
    autoEnetParSel : <boolean>
        Cross validated elastic net hyperparameter selection.
            - ``autoEnetParSel=True`` : peform a cross validation pre-hyperparameter search, s.t. RENT runs only with one hyperparamter setting.
            - ``autoEnetParSel=False`` : perform RENT with each combination of ``C`` and ``l1_ratios``.

    C : <list of int or float values>
        List holding regularisation parameters for K models. The lower,
        the stronger the regularization is .

    l1_ratios : <list of int or float values>
        List holding ratios between l1 and l2 penalty. Must be in [0,1]. For
        pure l2 use 0, for pure l1 use 1.
        
    poly : <str> 
        Create non-linear features.
            - ``poly='OFF'`` : no feature interaction.
            - ``poly='ON'`` : feature interaction and squared features (2-polynoms).
            - ``poly='ON_only_interactions'`` : only feature interactions, no squared features.

    testsize_range : <tuple float>
         Range of random proportion of dataset toinclude in test set,
         low and high are floats between 0 and 1, default (0.2, 0.6).
         Testsize can be fixed by setting low and high to the same value.

    K : <int>
        Number of unique train-test splits. Default ``K=100``.

    scale : <boolean>
        Scale each of the K train datasets. Default ``scale=True``.

    random_state : <None or int>
        Set a random state to reproduce your results. Default: ``random_state=None``.
        - ``random_state=None`` : no random seed. 
        - ``random_state={0,1,2,...}`` : random seed set.
        
    verbose : <int>
        Track the train process if value > 1. If value  = 1 only the overview
        of RENT input will be shown. Default ``verbose=0``.

    RETURNS
    ------
    class
        A class that contains the RENT-Regression model.
    """

    def __init__(self, data, target, feat_names=[], autoEnetParSel=True,
                 C=[1,10], l1_ratios = [0.6],
                 poly='OFF', testsize_range=(0.2, 0.6),
                 K=100, scale=True, random_state = None, verbose = 0):

        if any(c < 0 for c in C):
            sys.exit('C values must not be negative!')
        if any(l < 0 for l in l1_ratios) or any(l > 1 for l in l1_ratios):
            sys.exit('l1 ratios must be in [0,1]!')
        if autoEnetParSel not in [True, False]:
            sys.exit('autoEnetParSel must be True or False!')
        if scale not in [True, False]:
            sys.exit('scale must be True or False!')
        if poly not in ['ON', 'ON_only_interactions', 'OFF']:
            sys.exit('Invalid poly parameter!')
        # for testsize range criteria is missing.
        if K<=0:
            sys.exit('Invalid K!')
        if K<10:
            # does not show warning...
            warnings.warn('Attention: K is very small!', DeprecationWarning)

        # Print parameters for checking
        if verbose == 1:
            print('data dimension:', np.shape(data), ' data type:', type(data))
            print('target dimension', np.shape(target))
            print('regularization parameters C:', C)
            print('elastic net l1_ratios:', l1_ratios)
            print('number of models in ensemble:', K)
            print('scale:', scale)
            print('random state:', random_state)
            print('verbose:', verbose)


        # Define all objects needed later in methods below
        self.target = target
        self.K = K
        self.feat_names = feat_names
        self.scale = scale
        self.testsize_range = testsize_range
        self.verbose = verbose
        self.autoEnetParSel = autoEnetParSel
        self.random_state = random_state


        # Check if data is dataframe and add index information
        if isinstance(data, pd.DataFrame):
            self.indices = data.index
        else:
            self.indices = list(range(data.shape[0]))


        # If no feature names are given, then make some
        if len(self.feat_names) == 0:
            print('No feature names found - automatic generate feature names.')

            for ind in range(1, np.shape(data)[1] + 1):
                self.feat_names.append('f' + str(ind))


        # Extend data if poly was set to 'ON' or 'ON_only_interactions'
        if poly == 'ON':
            polynom = PolynomialFeatures(interaction_only=False, \
                                         include_bias=False)
            self.data = polynom.fit_transform(data)
            polynom_comb = list(combinations_with_replacement(self.feat_names,\
                                                              2))
            polynom_feat_names = []
            # Construct a new name for squares and interactions
            for item in polynom_comb:
                if item[0] == item[1]:
                    name = item[0] + '^2'
                else:
                    name = item[0] + '*' + item[1]
                polynom_feat_names.append(name)

            flist = list(self.feat_names)
            flist.extend(polynom_feat_names)
            self.feat_names = flist
            self.data = pd.DataFrame(self.data)
            self.data.index = self.indices
            self.data.columns = self.feat_names

        elif poly == 'ON_only_interactions':
            polynom = PolynomialFeatures(interaction_only=True,\
                                         include_bias=False)
            self.data = polynom.fit_transform(data)

            polynom_comb = list(combinations(self.feat_names, 2))
            polynom_feat_names = []

            # Construct a new name for squares and interactions
            for item in polynom_comb:
                name = item[0] + '*' + item[1]
                polynom_feat_names.append(name)

            flist = list(self.feat_names)
            flist.extend(polynom_feat_names)
            self.feat_names = flist
            self.data = pd.DataFrame(self.data)
            self.data.index = self.indices
            self.data.columns = self.feat_names

        elif poly == 'OFF':
            self.data = pd.DataFrame(data)
            self.data.index=self.indices
            self.data.columns = self.feat_names

        else:
            sys.exit('Value for paramter "poly" not regcognised.')


        if self.autoEnetParSel == True:
            self.C, self.l1_ratios = self.par_selection(C=C, l1_ratios=l1_ratios)
            self.C = [self.C]
            self.l1_ratios = [self.l1_ratios]
        else:
            self.C = C
            self.l1_ratios = l1_ratios


    def par_selection(self,
                    C,
                    l1_ratios,
                    n_splits=5,
                    testsize_range=(0.25,0.25)):
        """
        Preselect best `C` and `l1 ratio` with Cross Validation.

        PARAMETERS
        ----------
        C: <list of int or float values>
        List holding regularisation parameters for `K` models. The lower, the
        stronger the regularization is.

        l1_ratios: <list of int or float values>
            List holding ratios between l1 and l2 penalty. Must be in [0,1]. For
            pure l2 use 0, for pure l1 use 1.
        n_splits : <int>
            Number of cross validation folds. Default ``n_splits=5``.
            
        testsize_range: <tuple float>
            Range of random proportion of dataset toinclude in test set,
            low and high are floats between 0 and 1. Default ``testsize_range=(0.2, 0.6)``.
            Testsize can be fixed by setting low and high to the same value.

        RETURNS
        -------
        <tuple> 
        First entry: suggested `C` parameter.
        Second entry: suggested `l1 ratio`.

        """
        skf = KFold(n_splits=n_splits, random_state=self.random_state, shuffle=True)

        scores_df = pd.DataFrame(np.zeros, index=l1_ratios, columns=C)
        zeroes_df = pd.DataFrame(np.zeros, index=l1_ratios, columns=C)


        def run_parallel(l1):
            """
            Parallel computation of for ``K`` * ``C`` * ``l1_ratios`` models.

            PARAMETERS
            -----
            l1: current l1 ratio in the parallelization framework.
            """
            for reg in C:
                scores = list()
                zeroes = list()
                for train, test in skf.split(self.data, self.target):
                    # Find those parameters that are 0
                    if self.scale == True:
                        sc = StandardScaler()
                        train_data = sc.fit_transform(self.data.iloc[train,:])
                        train_target = self.target[train]
                        test_data_split = sc.transform(self.data.iloc[test,:])
                        test_target = self.target[test]
                    elif self.scale == False:
                        train_data = self.data.iloc[train,:].values
                        train_target = self.target[train]
                        test_data_split = self.data.iloc[test,:].values
                        test_target = self.target[test]

                    sgd =  ElasticNet(alpha=1/reg, l1_ratio=l1,
                                       max_iter=5000, 
                                       random_state=self.random_state, \
                                       fit_intercept=False).\
                                       fit(train_data, train_target)

                    mod_coef = sgd.coef_.reshape(1, len(sgd.coef_))
                    params = np.where(mod_coef != 0)[1]

                    # if there are parameters != 0, build a predicion model and
                    # find best parameter combination w.r.t. scoring
                    if len(params) == 0:
                        scores.append(np.nan)
                        zeroes.append(np.nan)
                    else:
                        zeroes.append((len(self.data.columns)-len(params))\
                                      /len(self.data.columns))


                        train_data_1 = train_data[:,params]
                        test_data_1 = test_data_split[:, params]

                        model = LinearRegression().\
                                fit(train_data_1, train_target)
                        scores.append(r2_score(test_target, \
                                        model.predict(test_data_1)))

                scores_df.loc[l1, reg] = np.nanmean(scores)
                zeroes_df.loc[l1, reg] = np.nanmean(zeroes)


        Parallel(n_jobs=-1, verbose=0, backend="threading")(
             map(delayed(run_parallel), l1_ratios))

        if len(np.unique(scores_df.values)) ==1:
            best_row, best_col = np.where(zeroes_df.values == \
                                                  np.nanmax(zeroes_df.values))
            best_l1 = zeroes_df.index[np.nanmax(best_row)]
            best_C = zeroes_df.columns[np.nanmin(best_col)]
        else:
            normed_scores = pd.DataFrame(self.min_max(scores_df.values))
            # normed_scores = (scores_df-np.nanmin(scores_df.values))\
            # /(np.nanmax(scores_df.values)-np.nanmin(scores_df.values))
            normed_zeroes = pd.DataFrame(self.min_max(zeroes_df.values))
            # normed_zeroes = (zeroes_df-np.nanmin(zeroes_df.values))\
            # /(np.nanmax(zeroes_df.values)-np.nanmin(zeroes_df.values))

            combination = 2 * ((normed_scores.copy().applymap(self.inv) + \
                           normed_zeroes.copy().applymap(self.inv)
                           ).applymap(self.inv))
            combination.index = scores_df.index.copy()
            combination.columns = scores_df.columns.copy()
            best_combination_row, best_combination_col = np.where(combination == \
                                                      np.nanmax(combination.values))
            best_l1 = combination.index[np.nanmax(best_combination_row)]
            best_C = combination.columns[np.nanmin(best_combination_col)]

        self._scores_df_cv, self._zeroes_df_cv, self._combination_cv = \
            scores_df, zeroes_df, combination

        self._scores_df_cv.columns.name = 'Scores'
        self._zeroes_df_cv.columns.name = 'Zeroes'
        self._combination_cv.columns.name = 'Harmonic Mean'
        return(best_C, best_l1)

    def run_parallel(self, K):
        """
        Parallel computation of ``K`` * ``len(C)`` * ``len(l1_ratios)`` models.

        PARAMETERS
        -----
        ``K`` : range of train-test splits
        """

        # Loop through all C
        for C in self.C:
            # Loop through requested number of tt splits
            for l1 in self.l1_ratios:
                
                if self.random_state == None:
                    X_train, X_test, y_train, y_test = train_test_split(
                              self.data, self.target,
                              test_size=self.random_testsizes[K],
                              random_state=None)
                else:
                    X_train, X_test, y_train, y_test = train_test_split(
                              self.data, self.target,
                              test_size=self.random_testsizes[K],
                              random_state=K)

#                self.train_sets.append(X_train)
                self.X_test = X_test

                # Initialise standard scaler and compute mean and STD from
                # training data.
                # Transform train and test dataset
                if self.scale == True:
                    sc = StandardScaler()
                    sc.fit(X_train)
                    X_train_std = sc.transform(X_train)
                    X_test_std = sc.transform(X_test)
                if self.scale == False:
                    X_train_std = X_train.copy().values
                    X_test_std = X_test.copy().values

                if self.verbose > 1:
                    print('l1 = ', l1, 'C = ', C, ', TT split = ', K)

                model = ElasticNet(alpha=1/C, l1_ratio=l1,
                                       max_iter=5000, random_state=self.random_state, \
                                       fit_intercept=False).\
                                       fit(X_train_std, y_train)

                # Get all weights (coefficients). Those that were selected
                # are non-zero, otherwise zero
                mod_coef = model.coef_.reshape(1, len(model.coef_))
                self.weight_dict[(C, l1, K)] = mod_coef
                self.weight_list.append(mod_coef)

                pred = model.predict(X_test_std)
                abs_error_df = pd.DataFrame({'abs error': abs(y_test-pred)})
                abs_error_df.index = X_test.index
                self.predictions_abs_errors[(C, l1, K)] = abs_error_df

                score = r2_score(y_test,pred)
                self.score_dict[(C, l1, K)] = score
                self.score_list.append(score)


    def train(self):
        """
        This method trains ``K`` * ``len(C)`` * ``len(l1_ratios)`` models in total. The number
        of models using the same hyperparamters is ``K``.
        For each model elastic net regularisation is applied for variable selection. Internally, train
        calls the ``run_parallel()`` function.
        """
        #check if this is needed and does what it should (probably doesn't work because of parallelization)
        np.random.seed(0)
        self.random_testsizes = np.random.uniform(self.testsize_range[0],
                                                  self.testsize_range[1],
                                                  self.K)

        # Initiate a dictionary holding coefficients for each model. Keys are
        # (C, K, num_w_init)
        self.weight_dict = {}

        # Initiate a dictionary holding computed performance metric for each
        self.score_dict = {}


        # Collect all coefs in a list that will be converted to a numpy array
        self.weight_list = []

        # Collect all coefs in a list that will be converted to a numpy array
        self.score_list = []

        # Initialize a dictionary to predict incorrect labels
        self.predictions_abs_errors = {}

        # stop runtime
        start = time.time()
        # Call parallelization function
        Parallel(n_jobs=-1, verbose=0, backend='threading')(
             map(delayed(self.run_parallel), range(self.K)))
        ende = time.time()
        self._runtime = ende-start

        # find best parameter setting and matrices
        result_list=[]
        for l1 in self.l1_ratios:
            for C in self.C:
                spec_result_list = []
                for k in self.score_dict.keys():
                    if k[0] == C and k[1] ==l1:
                        spec_result_list.append(self.score_dict[k])
                result_list.append(spec_result_list)

        means=[]
        for r in range(len(result_list)):
            means.append(np.mean(result_list[r]))

        self._scores_df = pd.DataFrame(np.array(means).reshape(\
                                  len(self.l1_ratios), \
                                  len(self.C)), \
        index= self.l1_ratios, columns = self.C)

        self._zeroes_df = pd.DataFrame(index = self.l1_ratios,\
                                   columns=self.C)
        for l1 in self.l1_ratios:
            for C in self.C:
                count = 0
                for K in range(self.K):
                    nz = \
                    len(np.where(pd.DataFrame(self.weight_dict[(C, l1, K)\
])==0)[0])
                    count = count + nz / len(self.feat_names)
                count = count / (self.K)
                self._zeroes_df.loc[l1, C] = count

        if len(self.C)>1 or len(self.l1_ratios)>1:
            normed_scores = pd.DataFrame(self.min_max(self._scores_df.copy().values))
            normed_zeroes = pd.DataFrame(self.min_max(self._zeroes_df.copy().values))
            normed_zeroes = normed_zeroes.astype('float')

            self._combination = 2 * ((normed_scores.copy().applymap(self.inv) + \
                                        normed_zeroes.copy().applymap(
                                            self.inv)).applymap(self.inv))
        else:
            self._combination = 2 * ((self._scores_df.copy().applymap(self.inv) + \
                                 self._zeroes_df.copy().applymap(
                                     self.inv)).applymap(self.inv))
        self._combination.index = self._scores_df.index.copy()
        self._combination.columns = self._scores_df.columns.copy()

        self._scores_df.columns.name = 'Scores'
        self._zeroes_df.columns.name = 'Zeroes'
        self._combination.columns.name = 'Harmonic Mean'

        best_row, best_col  = np.where(
            self._combination == np.nanmax(self._combination.values))
        self._best_l1_ratio = self._combination.index[np.nanmax(best_row)]
        self._best_C = self._combination.columns[np.nanmin(best_col)]

    def summary_objects(self):
        """
        This method computes a summary of average absolute errors for each sample
        across all ``K`` models, where the sample was part of at least one test set.

        Returns
        -------
        <pandas dataframe>

        """
        if not hasattr(self, '_best_C'):
            sys.exit('Run train() first!')

        self.incorrect_labels = pd.DataFrame({'# test':np.repeat\
                                      (0, np.shape(self.data)[0]),
                                      'average abs error':np.repeat\
                                      (0, np.shape(self.data)[0])})
        self.incorrect_labels.index=self.indices.copy()

        specific_predictions = []
        for K in range(self.K):
            specific_predictions.append(self.predictions_abs_errors[
                (self._best_C, self._best_l1_ratio, K)])
        self._histogram_data = pd.concat(specific_predictions, axis=1)
        self._histogram_data.columns = ['mod {0}'.format(x+1) \
                                        for x in range(
                                                self._histogram_data.shape[1])]
        count = self._histogram_data.count(axis=1)
        avg_abs_error = np.nanmean(self._histogram_data, axis=1)

        summary_df = pd.DataFrame({'count': count, 'avgerror': avg_abs_error})
        summary_df.index = self._histogram_data.index

        self.incorrect_labels.loc[summary_df.index,'# test'] = \
        summary_df.loc[:,'count']
        self.incorrect_labels.loc[summary_df.index,'average abs error'] = \
        summary_df.loc[:,'avgerror']

        self.incorrect_labels.iloc[ \
            np.where(self.incorrect_labels.iloc[:,0] == 0)[0]] = np.nan

        return self.incorrect_labels

    def get_object_errors(self):
        """
        Absolute errors for samples which were at least once in a test-set among ``K``
        models

        Returns
        -------
        <pandas dataframe>
        Matrix. Rows represent objects, columns represent genrated variables.

        """
        if not hasattr(self, '_histogram_data'):
            sys.exit('Run summary_objects() first!')
        return self._histogram_data

    def plot_object_errors(self, object_id, binning='auto', lower=0,
                                  upper=100, kde=False, norm_hist=False):
        """
        Histograms of absolute errors.

        PARAMETERS
        ----------
        object_id : <list of int or str>
            Samples/Objects whos histograms shall be plotted.
        lower : <float>
            Lower bound of the x-axis. Default ``lower=0``.
        upper : <float>
            Upper bound of the x-axis. Default ``upper=100``.
        kde : <boolean>
            Kernel density estimation, from `seaborn distplot`.
            Default: ``kde=False``.
        norm_hist : <boolean>
            Normalize the histogram, from `seaborn distplot`.
            Default: ``norm_hist=False``.
        """
        if not hasattr(self, '_histogram_data'):
            sys.exit('Run summary_objects() first!')
        # different binning schemata
        # https://www.answerminer.com/blog/binning-guide-ideal-histogram
        for obj in object_id:
            fig, ax = plt.subplots()
            data = self._histogram_data.loc[obj,:].dropna()
            if binning == "auto":
                bins = None
            if binning == "rice":
                bins = math.ceil(2 * len(data) ** (1./3.))
            if binning == "sturges":
                bins = math.ceil(math.log(len(data), 2)) + 1

            sns.set_style("white")
            ax=sns.distplot(data,
                            bins=bins,
                            color = 'darkblue',
                            hist_kws={'edgecolor':'darkblue'},
                            kde_kws={'linewidth': 3},
                            kde=kde,
                            norm_hist=norm_hist)
            ax.set(xlim=(lower, upper))

            if norm_hist == False:
                ax.set_ylabel('absolute frequencies', fontsize=10)
                ax.set_xlabel('Absolute Error', fontsize=10)
            else:
                ax.set_ylabel('frequencies')
                ax.set_xlabel('Absolute Error')
            ax.set_title('Object: {0}')

    def validation_study(self, test_data, test_labels,
                          num_drawings, num_permutations, alpha=0.05):
        """
        Two validation studies based on a statistical `t`-test. The null-hypotheses claims that
            -RENT is not better than random feature selection.
            -RENT performs equally on the real and a randomly permutated target.

        PARAMETERS
        ----------
        test_data : <numpy array> or <pandas dataframe>
            Dataset, used to evalute Logistic Models in the validation study.
            Dimension according to the paper: I_test x N
        test_lables: <numpy array> or <pandas dataframe>
            Response variable of the dataset.
            Dimension: I_train x 1 or I_train x 0 when an row-array is used.
        num_drawings: <int>
            Number of independent feature subset drawings for VS1, more information given in the paper.
        num_permutations: <int>
            Number of independent test_labels permutations for VS2, more information given in the paper.
        alpha: <float>
            Significance level for the `t`-test. Default ``alpha=0.05``.
        """
        if not hasattr(self, 'sel_var'):
            sys.exit('Run selectFeatures() first!')
        if self.scale == True:
            sc = StandardScaler()
            train_RENT = sc.fit_transform(self.data.iloc[:,self.sel_var])
            test_RENT = sc.transform(test_data.loc[:, self.sel_var])
        elif self.scale == False:
            train_RENT = self.data.iloc[:,self.sel_var].values
            test_RENT = test_data.loc[:, self.sel_var].values

        model = LinearRegression().fit(train_RENT,self.target)
        score = r2_score(test_labels, model.predict(test_RENT))
        # VS1
        VS1 = []
        for K in range(num_drawings):
            # Randomly select features (# features = # RENT features selected)
            columns = np.random.RandomState(seed=K).choice(
                range(0,len(self.data.columns)),
                                    len(self.sel_var))

            if self.scale == True:
                sc = StandardScaler()
                train_VS1 = sc.fit_transform(self.data.iloc[:, columns])
                test_VS1 = sc.transform(test_data.iloc[:, columns])
            elif self.scale == False:
                train_VS1 = self.data.iloc[:, columns].values
                test_VS1 = test_data.iloc[:, columns].values

            model = LinearRegression().fit(train_VS1,self.target)

            VS1.append(r2_score(test_labels, model.predict(test_VS1)))

        T = (np.mean(VS1) - score) / (np.std(VS1,ddof=1) / np.sqrt(len(VS1)))
        print("mean VS1", np.mean(VS1))
        p_value_VS1 = t.cdf(T, len(VS1)-1)
        print("VS1: p-value for average score from random feature drawing: ", p_value_VS1)

        if p_value_VS1 <= alpha:
            print('With a significancelevel of ', alpha, ' H0 is rejected.')
        else:
            print('With a significancelevel of ', alpha, ' H0 is accepted.')
        print(' ')
        print('-----------------------------------------------------------')
        print(' ')
        test_data.columns = self.data.columns
        VS2 = []
        if self.scale == True:
            sc = StandardScaler()
            train_VS2 = sc.fit_transform(self.data.iloc[:,self.sel_var])
            test_VS2 = sc.transform(test_data.loc[:, self.sel_var])
        elif self.scale == False:
            train_VS2 = self.data.iloc[:,self.sel_var].values
            test_VS2 = test_data.loc[:, self.sel_var].values

        model = LinearRegression().fit(train_VS2,self.target)
        for K in range(num_permutations):
            VS2.append(r2_score(
                    np.random.RandomState(seed=K).permutation(test_labels),\
                    model.predict(test_VS2)))

        print("Mean VS2", np.mean(VS2))
        T = (np.mean(VS2) - score) / (np.std(VS2,ddof=1) / np.sqrt(len(VS2)))
        p_value_VS2 = t.cdf(T, len(VS2)-1)
        print("VS2: p-value for score from permutation of test labels: ", p_value_VS2)

        if p_value_VS2 <= alpha:
            print('With a significancelevel of ', alpha, ' H0 is rejected.')
        else:
            print('With a significancelevel of ', alpha, ' H0 is accepted.')

        plt.figure(figsize=(15, 7))
        sns.kdeplot(VS1, shade=True, color="b", label='VS1')
        sns.kdeplot(VS2, shade=True, color="g", label='VS2')
        plt.axvline(x=score, color='r', linestyle='--',
                    label='RENT prediction score')
        plt.legend(prop={'size': 12})
        plt.ylabel('density', fontsize=14)
        plt.xticks(fontsize=12)
        plt.yticks(fontsize=12)
        plt.title('validation Study', fontsize=18)
