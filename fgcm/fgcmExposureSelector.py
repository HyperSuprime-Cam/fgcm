from __future__ import print_function

import numpy as np
import os
import sys
import esutil

from fgcmUtilities import expFlagDict

from sharedNumpyMemManager import SharedNumpyMemManager as snmm

class FgcmExposureSelector(object):
    """
    """
    def __init__(self,fgcmConfig,fgcmPars):

        self.fgcmLog = fgcmConfig.fgcmLog

        self.fgcmLog.info('Initializing FgcmExposureSelector')
        self.fgcmPars = fgcmPars

        # and config variables...
        self.minStarPerExp = fgcmConfig.minStarPerExp
        self.minExpPerNight = fgcmConfig.minExpPerNight
        self.expGrayPhotometricCut = fgcmConfig.expGrayPhotometricCut
        self.expVarGrayPhotometricCut = fgcmConfig.expVarGrayPhotometricCut
        self.expGrayHighCut = fgcmConfig.expGrayHighCut
        self.expGrayInitialCut = fgcmConfig.expGrayInitialCut

    def selectGoodExposures(self):
        """
        """

        # this cuts on expgray,vargray
        # based on those in the parameter file if they're available

        self.fgcmPars.expFlag[:] = 0

        bad,=np.where(self.fgcmPars.compNGoodStarPerExp == 0)
        self.fgcmPars.expFlag[bad] |= expFlagDict['NO_STARS']
        self.fgcmLog.info('Flagged %d bad exposures with no stars' % (bad.size))

        bad,=np.where((self.fgcmPars.compNGoodStarPerExp < self.minStarPerExp) &
                      (self.fgcmPars.compNGoodStarPerExp > 0))
        self.fgcmPars.expFlag[bad] |= expFlagDict['TOO_FEW_STARS']
        self.fgcmLog.info('Flagged %d bad exposures with too few stars.' % (bad.size))

        #bad,=np.where((self.fgcmPars.compExpGray < self.expGrayPhotometricCut) &
        #              (self.fgcmPars.compNGoodStarPerExp > 0))
        bad,=np.where((self.fgcmPars.compExpGray <
                       self.expGrayPhotometricCut[self.fgcmPars.expBandIndex]) &
                      (self.fgcmPars.compNGoodStarPerExp > 0))

        self.fgcmPars.expFlag[bad] |= expFlagDict['EXP_GRAY_TOO_NEGATIVE']
        self.fgcmLog.info('Flagged %d bad exposures with EXP_GRAY too negative.' % (bad.size))

        bad,=np.where((self.fgcmPars.compExpGray >
                       self.expGrayHighCut[self.fgcmPars.expBandIndex]) &
                      (self.fgcmPars.compNGoodStarPerExp > 0))
        self.fgcmPars.expFlag[bad] |= expFlagDict['EXP_GRAY_TOO_POSITIVE']
        self.fgcmLog.info('Flagged %d bad exposures with EXP_GRAY too positive.' % (bad.size))

        bad,=np.where(self.fgcmPars.compVarGray > self.expVarGrayPhotometricCut)
        self.fgcmPars.expFlag[bad] |= expFlagDict['VAR_GRAY_TOO_LARGE']
        self.fgcmLog.info('Flagged %d bad exposures with VAR_GRAY too large.' % (bad.size))

        good,=np.where(self.fgcmPars.expFlag == 0)
        self.fgcmLog.info('There are now %d of %d exposures that are "photometric"' %
                         (good.size,self.fgcmPars.nExp))

        ## MAYBE: do we want to consider minCCDPerExp?

    def selectGoodExposuresInitialSelection(self, fgcmGray):
        """
        """

        expGrayForInitialSelection = snmm.getArray(fgcmGray.expGrayForInitialSelectionHandle)
        expNGoodStarForInitialSelection = snmm.getArray(fgcmGray.expNGoodStarForInitialSelectionHandle)

        if (np.max(expNGoodStarForInitialSelection) == 0):
            self.fgcmLog.info('ERROR: Must run FgcmGray.computeExpGrayForInitialSelection before FgcmExposureSelector')
            raise ValueError("Must run FgcmGray.computeExpGrayForInitialSelection before FgcmExposureSelector")

        # reset all exposure flags
        self.fgcmPars.expFlag[:] = 0

        bad,=np.where(expNGoodStarForInitialSelection < self.minStarPerExp)
        self.fgcmPars.expFlag[bad] |= expFlagDict['TOO_FEW_STARS']
        self.fgcmLog.info('Flagged %d bad exposures with too few stars' % (bad.size))

        bad,=np.where(expGrayForInitialSelection < self.expGrayInitialCut)
        self.fgcmPars.expFlag[bad] |= expFlagDict['EXP_GRAY_TOO_NEGATIVE']
        self.fgcmLog.info('Flagged %d bad exposures with EXP_GRAY (initial) too large.' % (bad.size))

        good,=np.where(self.fgcmPars.expFlag == 0)
        self.fgcmLog.info('There are now %d of %d exposures that are potentially "photometric"' %
                         (good.size,self.fgcmPars.nExp))



    def selectCalibratableNights(self):
        """
        """

        # this will use existing flags...

        # select good exposures,
        #  limit to those that are in the fit bands
        goodExp,=np.where((self.fgcmPars.expFlag == 0) &
                          (~self.fgcmPars.expExtraBandFlag))

        # we first need to look for the good nights
        nExpPerNight=esutil.stat.histogram(self.fgcmPars.expNightIndex[goodExp],min=0,
                                max=self.fgcmPars.nCampaignNights-1)

        badNights,=np.where(nExpPerNight < self.minExpPerNight)

        self.fgcmLog.info('Flagging exposures on %d bad nights with too few photometric exposures.' % (badNights.size))

        # and we need to use *all* the exposures to flag bad nights
        h,rev = esutil.stat.histogram(self.fgcmPars.expNightIndex,min=0,
                                      max=self.fgcmPars.nCampaignNights-1,rev=True)

        for badNight in badNights:
            i1a=rev[rev[badNight]:rev[badNight+1]]

            self.fgcmPars.expFlag[i1a] |= expFlagDict['TOO_FEW_EXP_ON_NIGHT']

        bad,=np.where((self.fgcmPars.expFlag & expFlagDict['TOO_FEW_EXP_ON_NIGHT']) > 0)
        self.fgcmLog.info('Flagged %d exposures on bad nights.' % (bad.size))
