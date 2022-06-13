import warnings
from typing import Any

from botorch.models.kernels.categorical import CategoricalKernel
from gpytorch.kernels import MaternKernel, ScaleKernel
from gpytorch.constraints.constraints import Interval
from gpytorch.likelihoods.gaussian_likelihood import GaussianLikelihood
from gpytorch.priors import LogNormalPrior, HorseshoePrior
import numpy as np

from smac.epm.globally_augmented_local_gp import GloballyAugmentedLocalGP
from smac.facade.smac_hpo_facade import SMAC4HPO
from smac.optimizer.local_bo.rh2epm_boing import RunHistory2EPM4ScaledLogCostWithRaw
from smac.optimizer.local_bo.epm_chooser_boing import EPMChooserBOinG


class SMAC4BOING(SMAC4HPO):
    """
    SMAC facade for  BO inside Grove(BOinG):
        Deng and Lindauer, Searching in the Forest for Local Bayesian Optimization
        https://arxiv.org/abs/2111.05834
    This is a two-stages optimizer: at the first stage, the global optimizer extracts the global optimum with a random
    forest (RF) model. Then in the second stage, the optimizer constructs a local model in the vicinity of the
    configuration suggested by the global surrogate model.
    """
    def __init__(self, **kwargs: Any):
        kwargs['runhistory2epm'] = kwargs.get('runhistory2epm', RunHistory2EPM4ScaledLogCostWithRaw)
        smbo_kwargs = kwargs.get('smbo_kwargs', {})
        if smbo_kwargs == None:
            smbo_kwargs = {'epm_chooser', EPMChooserBOinG}
        if not isinstance(smbo_kwargs.get('epm_chooser', EPMChooserBOinG), EPMChooserBOinG):
            warnings.warn('BOinG must have EPMChooserBOinG as its epm_chooser!')
            smbo_kwargs['epm_chooser'] = EPMChooserBOinG
        epm_chooser_kwargs = smbo_kwargs.get('epm_chooser_kwargs', None)

        if epm_chooser_kwargs is None or epm_chooser_kwargs.get('model_local') is None:
            cont_kernel_kwargs = {'lengthscale_constraint': Interval(np.exp(-6.754111155189306),
                                                                     np.exp(0.0858637988771976),
                                                                     transform=None,
                                                                     initial_value=1.0
                                                                     ),
                                  }
            cat_kernel_kwargs = {'lengthscale_constraint': Interval(np.exp(-6.754111155189306),
                                                                    np.exp(0.0858637988771976),
                                                                    transform=None,
                                                                    initial_value=1.0
                                                                    ),
                                 }
            scale_kernel_kwargs = {'outputscale_constraint': Interval(np.exp(-10.),
                                                                      np.exp(2.),
                                                                      transform=None,
                                                                      initial_value=2.0
                                                                      ),
                                   'outputscale_prior': LogNormalPrior(0.0, 1.0),
                                   }

            kernel_kwargs = {
                'cont_kernel': MaternKernel,
                'cont_kernel_kwargs': cont_kernel_kwargs,
                'cat_kernel': CategoricalKernel,
                'cat_kernel_kwargs': cat_kernel_kwargs,
                'scale_kernel': ScaleKernel,
                'scale_kernel_kwargs': scale_kernel_kwargs,
            }

            # by setting lower bound of noise_constraint we could make it more stable
            noise_prior = HorseshoePrior(0.1)
            likelihood = GaussianLikelihood(
                noise_prior=noise_prior,
                noise_constraint=Interval(1e-5, np.exp(2), transform=None)
            ).double()

            if epm_chooser_kwargs is None:
                smbo_kwargs['epm_chooser_kwargs'] = {"model_local": GloballyAugmentedLocalGP,
                                                     "model_local_kwargs": dict(kernel_kwargs=kernel_kwargs,
                                                                                likelihood=likelihood)}
            else:
                smbo_kwargs['epm_chooser_kwargs'].update({"model_local": GloballyAugmentedLocalGP,
                                                          "model_local_kwargs": dict(kernel_kwargs=kernel_kwargs,
                                                                                     likelihood=likelihood)})
        kwargs['smbo_kwargs'] = smbo_kwargs

        if kwargs.get('random_configuration_chooser') is None:
            # follows SMAC4BB
            random_config_chooser_kwargs = kwargs.get(
                'random_configuration_chooser_kwargs',
                dict(),
            ) or dict()
            random_config_chooser_kwargs['prob'] = random_config_chooser_kwargs.get('prob', 0.08447232371720552)
            kwargs['random_configuration_chooser_kwargs'] = random_config_chooser_kwargs

        super().__init__(**kwargs)

        if self.solver.scenario.n_features > 0:
            raise NotImplementedError("BOinG cannot handle instances")

        self.solver.scenario.acq_opt_challengers = 1000  # type: ignore[attr-defined] # noqa F821
        # activate predict incumbent
        self.solver.epm_chooser.predict_x_best = True
