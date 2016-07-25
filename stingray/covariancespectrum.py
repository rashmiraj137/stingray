# -*- coding: utf-8 -*-
from __future__ import division
import collections
import numpy as np

from stingray import Lightcurve
import stingray.utils as utils

__all__ = ['Covariancespectrum', 'AveragedCovariancespectrum']


class Covariancespectrum(object):

    def __init__(self, event_list, dt, band_interest=None,
                 ref_band_interest=None, std=None):
        """
        Parameters
        ----------
        event_list : numpy 2D array
            A numpy 2D array with first column as time of arrival and second
            column as photon energies associated.

        dt : float
            The time resolution of the Lightcurve formed from the energy bin.

        band_interest : iterable of tuples, default All
            An iterable of tuples with minimum and maximum values of the range
            in the band of interest. e.g list of tuples, tuple of tuples.

        ref_band_interest : tuple of reference band range, default All
            A tuple with minimum and maximum values of the range in the band
            of interest in reference channel.

        std : float or np.array or list of numbers
            The term std is used to cacluate the excess variance of a band.
            If std is set to None, default Poisson case is taken and the
            std is calculated as `mean(lc)**0.5`. In the case of a single
            float as input, the same is used as the standard deviation which
            is also used as the std. And if the std is an iterable of
            numbers, their mean is used for the same purpose.


        Attributes
        ----------
        energy_events : dictionary
            A dictionary with energy bins as keys and time of arrivals of
            photons with the same energy as value.

        energy_covar : dictionary
            A dictionary with mid point of band_interest and their covariance
            computed with their individual reference band. The covaraince
            values are normalized.

        unnorm_covar : np.ndarray
            An array of arrays with mid point band_interest and their
            covariance. It is the array-form of the dictionary `energy_covar`.
            The covariance values are unnormalized.

        covar : np.ndarray
            Normalized covaraiance spectrum.

        covar_error : np.ndarray
            Errors of the normalized covariance spectrum.

        min_time : int
            Time of arrival of the earliest photon.

        max_time : int
            Time of arrival of the last photon.

        min_energy : float
            Energy of the photon with the minimum energy.

        max_energy : float
            Energy of the photon with the maximum energy.

        Reference
        ---------
        [1] Wilkinson, T. and Uttley, P. (2009), Accretion disc variability
            in the hard state of black hole X-ray binaries. Monthly Notices
            of the Royal Astronomical Society, 397: 666–676.
            doi: 10.1111/j.1365-2966.2009.15008.x
        """
        self._init_vars(event_list, dt, band_interest,
                        ref_band_interest, std)

        self._construct_energy_events()

        self._update_energy_events()

        self._construct_energy_covar()

    def _init_vars(self, event_list, dt, band_interest,
                   ref_band_interest, std):
        self.event_list = event_list

        # Sorted by energy values as second row
        self.event_list_T = event_list[self.event_list[:, 1].argsort()].T

        self.min_energy = np.min(self.event_list_T[1])
        self.max_energy = np.max(self.event_list_T[1])
        self.min_time = np.min(self.event_list_T[0])
        self.max_time = np.max(self.event_list_T[0])

        if ref_band_interest is None:
            ref_band_interest = (self.min_energy, self.max_energy)

        assert type(ref_band_interest) in (list, tuple), "Ref Band interest " \
                                                         "should be either " \
                                                         "tuple or list."

        assert len(ref_band_interest) == 2, "Band interest should be a tuple" \
                                            " with min and max energy value " \
                                            "for the reference band."
        self.ref_band_interest = ref_band_interest

        if band_interest is not None:
            for element in list(band_interest):
                assert type(element) in (list, tuple), \
                    "band_interest should be iterable of either tuple or list."
                assert len(element) == 2, "Band interest should be a tuple " \
                                          "with min and max energy values."

        self.band_interest = band_interest
        self.dt = dt

        self.std = std

    def _construct_energy_events(self):

        least_count = np.diff(np.unique(self.event_list_T[1])).min()

        # An array of unique energy values
        unique_energy = np.unique(self.event_list_T[1])

        # A dictionary with energy bin as key and events as value of the key
        self.energy_events = {}

        for i in range(len(unique_energy) - 1):
            self.energy_events[unique_energy[i] + least_count*0.5] = []

        # Add time of arrivals to corresponding energy bins
        # For each bin except the last one, the lower bound is included and
        # the upper bound is excluded.
        for energy in self.energy_events.keys():
            # The last energy bin
            if energy == self.max_energy - least_count*0.5:
                toa = self.event_list_T[0][np.logical_and(
                    self.event_list_T[1] >= energy - least_count*0.5,
                    self.event_list_T[1] <= energy + least_count*0.5)]
                self.energy_events[energy] = sorted(toa)
            else:
                toa = self.event_list_T[0][np.logical_and(
                    self.event_list_T[1] >= energy - least_count*0.5,
                    self.event_list_T[1] < energy + least_count*0.5)]
                self.energy_events[energy] = sorted(toa)

    def _update_energy_events(self):
        """
        In case of a specific band interest, merge the required energy bins
        into one with the new key as the mid-point of the band interest.
        """
        if self.band_interest is not None:
            energy_events_ = {}
            for band in list(self.band_interest):
                mid_bin = (band[0] + band[1]) / 2
                energy_events_[mid_bin] = []

                # Modify self.energy_events to form a band with one key
                for key in list(self.energy_events.keys()):
                    if key >= band[0] and key <= band[1]:
                        energy_events_[mid_bin] += self.energy_events[key]
                        del self.energy_events[key]

            self.energy_events.update(energy_events_)

    def _init_energy_covar(self):
        """
        Initialize the energy_covar dictionary for further computations.
        """
        # The dictionary with covariance spectrum for each energy bin
        self.energy_covar = {}

        # Initialize it with empty mapping
        if self.band_interest is None:
            for key in self.energy_events.keys():
                self.energy_covar[key] = []
        else:
            for band in list(self.band_interest):
                mid_bin = (band[0] + band[1]) / 2
                self.energy_covar[mid_bin] = []

        # Error in covariance
        self.covar_error = {}

    def _construct_energy_covar(self):
        """Form the actual output covaraince dictionary and array."""
        self._init_energy_covar()

        xs_var = dict()

        for energy in self.energy_covar.keys():
            lc = Lightcurve.make_lightcurve(
                    self.energy_events[energy], self.dt, tstart=self.min_time,
                    tseg=self.max_time - self.min_time)

            # Calculating timestamps for lc_ref
            toa_ref = []
            for key, value in self.energy_events.items():
                if key >= self.ref_band_interest[0] and \
                        key <= self.ref_band_interest[1]:
                    if key != energy:
                        toa_ref.extend(value)

            toa_ref = np.array(sorted(toa_ref))

            lc_ref = Lightcurve.make_lightcurve(
                    toa_ref, self.dt, tstart=self.min_time,
                    tseg=self.max_time - self.min_time)

            assert len(lc.time) == len(lc_ref.time)

            covar = self._compute_covariance(lc, lc_ref)

            self.energy_covar[energy] = covar

            self.covar_error[energy] = self._calculate_covariance_error(
                                            lc, lc_ref)

            # Excess variance in ref band
            xs_var[energy] = self._calculate_excess_variance(lc_ref)

        self.unnorm_covar = np.vstack(self.energy_covar.items())

        for key, value in self.energy_covar.items():
            if not xs_var[key] > 0:
                utils.simon("The excess variance in the reference band is "
                            "negative. This implies that the reference "
                            "band was badly chosen. Beware that the "
                            "covariance spectra will have NaNs!")
            self.energy_covar[key] = value / (xs_var[key])**0.5

        self.covar = np.vstack(self.energy_covar.items())
        self.covar_error = np.vstack(self.covar_error.items())

    def _calculate_excess_variance(self, lc):
        std = self._calculate_std(lc)
        return np.var(lc) - std**2

    def _calculate_std(self, lc):
        """Return std calculated for the possible types of `std`"""
        if self.std is None:
            std = np.mean(lc)**0.5
        elif isinstance(self.std, collections.Iterable):
            std = np.mean(self.std)  # Iterable of numbers
        else:  # Single float number
            std = self.std

        return std

    def _compute_covariance(self, lc1, lc2):
        """Calculate and return the covariance between two time series."""
        return np.cov(lc1.counts, lc2.counts)[0][1]

    def _calculate_covariance_error(self, lc_x, lc_y):
        """Calculate the error of the normalized covariance spectrum."""
        # Excess Variance of reference band
        xs_x = self._calculate_excess_variance(lc_x)
        # Standard deviation of light curve
        err_y = self._calculate_std(lc_y)
        # Excess Variance of reference band
        xs_y = self._calculate_excess_variance(lc_y)
        # Standard deviation of light curve
        err_x = self._calculate_std(lc_x)
        # Number of time bins in lightcurve
        N = lc_x.ncounts
        # Number of segments averaged
        M = 1

        num = xs_x*err_y + xs_y*err_x + err_x*err_y
        denom = N * M * xs_y

        return (num / denom)**0.5


class AveragedCovariancespectrum(Covariancespectrum):
    def __init__(self, event_list, dt, segment_size, band_interest=None,
                 ref_band_interest=None, std=None):
        """
        Make an averaged covariance spectrum by segmenting the light curve
        formed, calculating covariance for each segment and then averaging
        the resulting covariance spectra.

        Parameters
        ----------
        event_list : numpy 2D array
            A numpy 2D array with first column as time of arrival and second
            column as photon energies associated.

        dt : float
            The time resolution of the Lightcurve formed from the energy bin.

        segment_size : float
            The size of each segment to average. Note that if the total
            duration of each Lightcurve object formed is not an integer
            multiple of the segment_size, then any fraction left-over at the
            end of the time series will be lost.


        band_interest : iterable of tuples, default All
            An iterable of tuples with minimum and maximum values of the range
            in the band of interest. e.g list of tuples, tuple of tuples.

        ref_band_interest : tuple of reference band range, default All
            A tuple with minimum and maximum values of the range in the band
            of interest in reference channel.

        std : float or np.array or list of numbers
            The term std is used to cacluate the excess variance of a band.
            If std is set to None, default Poisson case is taken and the
            std is calculated as `mean(lc)**0.5`. In the case of a single
            float as input, the same is used as the standard deviation which
            is also used as the std. And if the std is an iterable of
            numbers, their mean is used for the same purpose.


        Attributes
        ----------
        energy_events : dictionary
            A dictionary with energy bins as keys and time of arrivals of
            photons with the same energy as value.

        energy_covar : dictionary
            A dictionary with mid point of band_interest and their covariance
            computed with their individual reference band. The covaraince
            values are normalized.

        unnorm_covar : np.ndarray
            An array of arrays with mid point band_interest and their
            covariance. It is the array-form of the dictionary `energy_covar`.
            The covariance values are unnormalized.

        covar : np.ndarray
            Normalized covaraiance spectrum.

        covar_error : np.ndarray
            Errors of the normalized covariance spectrum.

        min_time : int
            Time of arrival of the earliest photon.

        max_time : int
            Time of arrival of the last photon.

        min_energy : float
            Energy of the photon with the minimum energy.

        max_energy : float
            Energy of the photon with the maximum energy.

        """
        self._init_vars(event_list, dt, band_interest, ref_band_interest, std)
