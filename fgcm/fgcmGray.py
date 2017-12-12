from __future__ import print_function

import numpy as np
import os
import sys
import esutil
import time
import scipy.optimize

import matplotlib.pyplot as plt


from fgcmUtilities import gaussFunction
from fgcmUtilities import histoGauss
from fgcmUtilities import objFlagDict

from sharedNumpyMemManager import SharedNumpyMemManager as snmm

class FgcmGray(object):
    """
    """
    def __init__(self,fgcmConfig,fgcmPars,fgcmStars):

        self.fgcmLog = fgcmConfig.fgcmLog

        self.fgcmLog.info('Initializing fgcmGray')

        # need fgcmPars because it tracks good exposures
        #  also this is where the gray info is stored
        self.fgcmPars = fgcmPars

        # need fgcmStars because it has the stars (duh)
        self.fgcmStars = fgcmStars

        # and record configuration variables...
        self.minStarPerCCD = fgcmConfig.minStarPerCCD
        self.minStarPerExp = fgcmConfig.minStarPerExp
        self.minCCDPerExp = fgcmConfig.minCCDPerExp
        self.maxCCDGrayErr = fgcmConfig.maxCCDGrayErr
        #self.sigFgcmMaxErr = fgcmConfig.sigFgcmMaxErr
        #self.sigFgcmMaxEGray = fgcmConfig.sigFgcmMaxEGray
        self.ccdGrayMaxStarErr = fgcmConfig.ccdGrayMaxStarErr
        self.ccdStartIndex = fgcmConfig.ccdStartIndex
        self.illegalValue = fgcmConfig.illegalValue
        self.expGrayInitialCut = fgcmConfig.expGrayInitialCut
        self.plotPath = fgcmConfig.plotPath
        self.outfileBaseWithCycle = fgcmConfig.outfileBaseWithCycle
        self.cycleNumber = fgcmConfig.cycleNumber
        self.expGrayCheckDeltaT = fgcmConfig.expGrayCheckDeltaT
        #self.varNSig = fgcmConfig.varNSig
        #self.varMinBand = fgcmConfig.varMinBand
        self.expGraySmoothDeltaT = fgcmConfig.expGraySmoothDeltaT
        self.applyExpGraySmooth = fgcmConfig.applyExpGraySmooth

        self._prepareGrayArrays()

    def _prepareGrayArrays(self):
        """
        """

        # we have expGray for Selection
        self.expGrayForInitialSelectionHandle = snmm.createArray(self.fgcmPars.nExp,dtype='f8')
        self.expGrayRMSForInitialSelectionHandle = snmm.createArray(self.fgcmPars.nExp,dtype='f8')
        self.expNGoodStarForInitialSelectionHandle = snmm.createArray(self.fgcmPars.nExp,dtype='i4')

        # and the exp/ccd gray for the zeropoints

        self.ccdGrayHandle = snmm.createArray((self.fgcmPars.nExp,self.fgcmPars.nCCD),dtype='f8')
        self.ccdGrayRMSHandle = snmm.createArray((self.fgcmPars.nExp,self.fgcmPars.nCCD),dtype='f8')
        self.ccdGrayErrHandle = snmm.createArray((self.fgcmPars.nExp,self.fgcmPars.nCCD),dtype='f8')
        self.ccdNGoodObsHandle = snmm.createArray((self.fgcmPars.nExp,self.fgcmPars.nCCD),dtype='i4')
        self.ccdNGoodStarsHandle = snmm.createArray((self.fgcmPars.nExp,self.fgcmPars.nCCD),dtype='i4')
        self.ccdNGoodTilingsHandle = snmm.createArray((self.fgcmPars.nExp,self.fgcmPars.nCCD),dtype='f8')

        self.expGrayHandle = snmm.createArray(self.fgcmPars.nExp,dtype='f8')
        self.expGrayRMSHandle = snmm.createArray(self.fgcmPars.nExp,dtype='f8')
        self.expGrayErrHandle = snmm.createArray(self.fgcmPars.nExp,dtype='f8')
        self.expNGoodStarsHandle = snmm.createArray(self.fgcmPars.nExp,dtype='i4')
        self.expNGoodCCDsHandle = snmm.createArray(self.fgcmPars.nExp,dtype='i2')
        self.expNGoodTilingsHandle = snmm.createArray(self.fgcmPars.nExp,dtype='f8')

        #self.sigFgcm = np.zeros(self.fgcmPars.nBands,dtype='f8')

    def computeExpGrayForInitialSelection(self,doPlots=True):
        """
        """
        if (not self.fgcmStars.magStdComputed):
            raise ValueError("Must run FgcmChisq to compute magStd before computeExpGrayForInitialSelection")

        # Note this computes ExpGray for all exposures, good and bad

        startTime = time.time()
        self.fgcmLog.info('Computing ExpGray for initial selection')

        # useful numbers
        expGrayForInitialSelection = snmm.getArray(self.expGrayForInitialSelectionHandle)
        expGrayRMSForInitialSelection = snmm.getArray(self.expGrayRMSForInitialSelectionHandle)
        expNGoodStarForInitialSelection = snmm.getArray(self.expNGoodStarForInitialSelectionHandle)

        objID = snmm.getArray(self.fgcmStars.objIDHandle)
        objMagStdMean = snmm.getArray(self.fgcmStars.objMagStdMeanHandle)
        objMagStdMeanErr = snmm.getArray(self.fgcmStars.objMagStdMeanErrHandle)
        objNGoodObs = snmm.getArray(self.fgcmStars.objNGoodObsHandle)
        objFlag = snmm.getArray(self.fgcmStars.objFlagHandle)

        obsMagStd = snmm.getArray(self.fgcmStars.obsMagStdHandle)
        obsBandIndex = snmm.getArray(self.fgcmStars.obsBandIndexHandle)

        obsIndex = snmm.getArray(self.fgcmStars.obsIndexHandle)
        objObsIndex = snmm.getArray(self.fgcmStars.objObsIndexHandle)
        obsObjIDIndex = snmm.getArray(self.fgcmStars.obsObjIDIndexHandle)
        obsExpIndex = snmm.getArray(self.fgcmStars.obsExpIndexHandle)
        obsFlag = snmm.getArray(self.fgcmStars.obsFlagHandle)

        # first, we need to compute E_gray == <mstd> - mstd for each observation

        # compute all the EGray values

        EGray = np.zeros(self.fgcmStars.nStarObs,dtype='f8')
        EGray[obsIndex] = (objMagStdMean[obsObjIDIndex[obsIndex],obsBandIndex[obsIndex]] -
                           obsMagStd[obsIndex])

        # only use good observations of good stars...

        # for the required bands
        minObs = objNGoodObs[:,self.fgcmStars.bandRequiredIndex].min(axis=1)

        goodStars, = np.where((minObs >= self.fgcmStars.minPerBand) &
                              (objFlag == 0))

        # select observations of these stars...
        ##
        #_,goodObs=esutil.numpy_util.match(objID[goodStars],objID[obsObjIDIndex])
        #  NOTE: this relies on np.where returning a sorted array
        _,goodObs = esutil.numpy_util.match(goodStars,
                                            obsObjIDIndex,
                                            presorted=True)

        # and cut out bad observations
        gd,=np.where(obsFlag[goodObs] == 0)
        goodObs = goodObs[gd]

        self.fgcmLog.info('FgcmGray initial exp gray using %d observations from %d good stars.' %
                         (goodObs.size,goodStars.size))

        # and first, we only use the required bands
        _,reqBandUse = esutil.numpy_util.match(self.fgcmStars.bandRequiredIndex,
                                               obsBandIndex[goodObs])

        # now group per exposure and sum...

        expGrayForInitialSelection[:] = 0.0
        expGrayRMSForInitialSelection[:] = 0.0
        expNGoodStarForInitialSelection[:] = 0

        np.add.at(expGrayForInitialSelection,
                  obsExpIndex[goodObs[reqBandUse]],
                  EGray[goodObs[reqBandUse]])
        np.add.at(expGrayRMSForInitialSelection,
                  obsExpIndex[goodObs[reqBandUse]],
                  EGray[goodObs[reqBandUse]]**2.)
        np.add.at(expNGoodStarForInitialSelection,
                  obsExpIndex[goodObs[reqBandUse]],
                  1)

        # loop over the extra bands...
        #  we only want to use previously determined "good" stars
        for extraBandIndex in self.fgcmStars.bandExtraIndex:
            extraBandUse, = np.where((obsBandIndex[goodObs] == extraBandIndex) &
                                     (objNGoodObs[obsObjIDIndex[goodObs],extraBandIndex] >=
                                      self.fgcmStars.minPerBand))

            np.add.at(expGrayForInitialSelection,
                      obsExpIndex[goodObs[extraBandUse]],
                      EGray[goodObs[extraBandUse]])
            np.add.at(expGrayRMSForInitialSelection,
                      obsExpIndex[goodObs[extraBandUse]],
                      EGray[goodObs[extraBandUse]]**2.)
            np.add.at(expNGoodStarForInitialSelection,
                      obsExpIndex[goodObs[extraBandUse]],
                      1)


        gd,=np.where(expNGoodStarForInitialSelection > 0)
        expGrayForInitialSelection[gd] /= expNGoodStarForInitialSelection[gd]
        expGrayRMSForInitialSelection[gd] = np.sqrt((expGrayRMSForInitialSelection[gd]/expNGoodStarForInitialSelection[gd]) -
                                             (expGrayForInitialSelection[gd])**2.)

        self.fgcmLog.info('ExpGray for initial selection computed for %d exposures.' %
                         (gd.size))
        self.fgcmLog.info('Computed ExpGray for initial selection in %.2f seconds.' %
                         (time.time() - startTime))

        if (not doPlots):
            return

        expUse,=np.where((self.fgcmPars.expFlag == 0) &
                         (expNGoodStarForInitialSelection > self.minStarPerExp) &
                         (expGrayForInitialSelection > self.expGrayInitialCut))

        for i in xrange(self.fgcmPars.nBands):
            self.fgcmLog.debug('Making EXP_GRAY (initial) histogram for %s band' %
                               (self.fgcmPars.bands[i]))
            inBand, = np.where(self.fgcmPars.expBandIndex[expUse] == i)

            if (inBand.size == 0) :
                continue

            fig=plt.figure(1,figsize=(8,6))
            fig.clf()

            ax=fig.add_subplot(111)

            coeff = histoGauss(ax, expGrayForInitialSelection[expUse[inBand]])

            ax.tick_params(axis='both',which='major',labelsize=14)
            ax.locator_params(axis='x',nbins=5)

            text=r'$(%s)$' % (self.fgcmPars.bands[i]) + '\n' + \
                r'$\mathrm{Cycle\ %d}$' % (self.cycleNumber) + '\n' + \
                r'$\mu = %.5f$' % (coeff[1]) + '\n' + \
                r'$\sigma = %.4f$' % (coeff[2])

            ax.annotate(text,(0.95,0.93),xycoords='axes fraction',ha='right',va='top',fontsize=16)
            ax.set_xlabel(r'$\mathrm{EXP}^{\mathrm{gray}} (\mathrm{initial})$',fontsize=16)
            ax.set_ylabel(r'# of Exposures',fontsize=14)

            fig.savefig('%s/%s_initial_expgray_%s.png' % (self.plotPath,
                                                          self.outfileBaseWithCycle,
                                                          self.fgcmPars.bands[i]))


    def computeCCDAndExpGray(self,doPlots=True,onlyObsErr=False):
        """
        """

        if (not self.fgcmStars.allMagStdComputed):
            raise ValueError("Must run FgcmChisq to compute magStd before computeCCDAndExpGray")

        startTime = time.time()
        self.fgcmLog.info('Computing CCDGray and ExpGray.')

        # Note: this computes the gray values for all exposures, good and bad

        # values to set
        ccdGray = snmm.getArray(self.ccdGrayHandle)
        ccdGrayRMS = snmm.getArray(self.ccdGrayRMSHandle)
        ccdGrayErr = snmm.getArray(self.ccdGrayErrHandle)
        ccdNGoodObs = snmm.getArray(self.ccdNGoodObsHandle)
        ccdNGoodStars = snmm.getArray(self.ccdNGoodStarsHandle)
        ccdNGoodTilings = snmm.getArray(self.ccdNGoodTilingsHandle)

        expGray = snmm.getArray(self.expGrayHandle)
        expGrayRMS = snmm.getArray(self.expGrayRMSHandle)
        expGrayErr = snmm.getArray(self.expGrayErrHandle)
        expNGoodCCDs = snmm.getArray(self.expNGoodCCDsHandle)
        expNGoodStars = snmm.getArray(self.expNGoodStarsHandle)
        expNGoodTilings = snmm.getArray(self.expNGoodTilingsHandle)

        # input numbers
        objID = snmm.getArray(self.fgcmStars.objIDHandle)
        objMagStdMean = snmm.getArray(self.fgcmStars.objMagStdMeanHandle)
        objMagStdMeanErr = snmm.getArray(self.fgcmStars.objMagStdMeanErrHandle)
        objNGoodObs = snmm.getArray(self.fgcmStars.objNGoodObsHandle)
        objFlag = snmm.getArray(self.fgcmStars.objFlagHandle)

        obsMagStd = snmm.getArray(self.fgcmStars.obsMagStdHandle)
        obsMagErr = snmm.getArray(self.fgcmStars.obsMagADUErrHandle)
        obsBandIndex = snmm.getArray(self.fgcmStars.obsBandIndexHandle)
        obsCCDIndex = snmm.getArray(self.fgcmStars.obsCCDHandle) - self.ccdStartIndex

        obsIndex = snmm.getArray(self.fgcmStars.obsIndexHandle)
        objObsIndex = snmm.getArray(self.fgcmStars.objObsIndexHandle)
        obsObjIDIndex = snmm.getArray(self.fgcmStars.obsObjIDIndexHandle)
        obsExpIndex = snmm.getArray(self.fgcmStars.obsExpIndexHandle)
        obsFlag = snmm.getArray(self.fgcmStars.obsFlagHandle)

        # make sure we have enough obervations per band
        #  (this may be redundant)
        minObs = objNGoodObs[:,self.fgcmStars.bandRequiredIndex].min(axis=1)

        # select good stars...
        goodStars, = np.where((minObs >= self.fgcmStars.minPerBand) &
                              (objFlag == 0))

        # match the good stars to the observations
        _,goodObs = esutil.numpy_util.match(goodStars,
                                            obsObjIDIndex,
                                            presorted=True)

        # and filter out bad observations
        #  note that we want to compute for all exposures, so no exposure cut here
        gd,=np.where(obsFlag[goodObs] == 0)
        goodObs = goodObs[gd]

        # we need to compute E_gray == <mstd> - mstd for each observation
        # compute EGray, GO for Good Obs
        EGrayGO = (objMagStdMean[obsObjIDIndex[goodObs],obsBandIndex[goodObs]] -
                   obsMagStd[goodObs])
        # and need the error for Egray: sum in quadrature of individual and avg errs
        #EGrayErr2GO = (objMagStdMeanErr[obsObjIDIndex[goodObs],obsBandIndex[goodObs]]**2. +
        #               obsMagErr[goodObs]**2.)
        if (onlyObsErr):
            # only obs error ... use this option when doing initial guess at superstarflat
            EGrayErr2GO = obsMagErr[goodObs]**2.
        else:
            # take into account correlated average mag error
            EGrayErr2GO = (obsMagErr[goodObs]**2. -
                           objMagStdMeanErr[obsObjIDIndex[goodObs],obsBandIndex[goodObs]]**2.)

        # one more cut on the maximum error
        gd,=np.where(EGrayErr2GO < self.ccdGrayMaxStarErr)
        goodObs=goodObs[gd]
        EGrayGO=EGrayGO[gd]
        EGrayErr2GO=EGrayErr2GO[gd]

        self.fgcmLog.info('FgcmGray using %d observations from %d good stars.' %
                         (goodObs.size,goodStars.size))

        # HACK THIS TEMPORARILY
        if (1 == 0):
            import fitsio

            # we need to have an exposure cut!  Aieee!
            gdTemp,=np.where((self.fgcmPars.expFlag[obsExpIndex[goodObs]] == 0) &
                             (obsFlag[goodObs] == 0))

            tempCat = np.zeros(gdTemp.size, dtype=[('EGRAY','f4'),
                                                   ('EGRAYRAW','f4'),
                                                   ('EGRAYERR2','f4'),
                                                   ('BANDINDEX','i2'),
                                                   ('CCDINDEX','i2'),
                                                   ('EXPINDEX','i4'),
                                                   ('EPOCHINDEX','i2'),
                                                   ('RA','f8'),
                                                   ('DEC','f8'),
                                                   ('X','f4'),
                                                   ('Y','f4')])

            tempCat['EGRAY'][:] = EGrayGO[gdTemp]
            tempCat['EGRAYERR2'][:] = EGrayErr2GO[gdTemp]
            tempCat['BANDINDEX'][:] = obsBandIndex[goodObs[gdTemp]]
            tempCat['CCDINDEX'][:] = obsCCDIndex[goodObs[gdTemp]]
            tempCat['EXPINDEX'][:] = obsExpIndex[goodObs[gdTemp]]

            # remove the superstar
            tempCat['EGRAYRAW'][:] = tempCat['EGRAY'][:] + self.fgcmPars.expCCDSuperStar[obsExpIndex[goodObs[gdTemp]],obsCCDIndex[goodObs[gdTemp]]]
            tempCat['EPOCHINDEX'][:] = self.fgcmPars.expEpochIndex[obsExpIndex[goodObs[gdTemp]]]

            objRA = snmm.getArray(self.fgcmStars.objRAHandle)
            objDec = snmm.getArray(self.fgcmStars.objDecHandle)
            tempCat['RA'][:] = objRA[obsObjIDIndex[goodObs[gdTemp]]]
            tempCat['DEC'][:] = objDec[obsObjIDIndex[goodObs[gdTemp]]]

            obsX = snmm.getArray(self.fgcmStars.obsXHandle)
            obsY = snmm.getArray(self.fgcmStars.obsYHandle)
            tempCat['X'][:] = obsX[goodObs[gdTemp]]
            tempCat['Y'][:] = obsY[goodObs[gdTemp]]

            fitsio.write('temporary_egray_xy.fits', tempCat, clobber=True)

        #for bandIndex in xrange(self.fgcmPars.fitBandIndex):
            # which observations are considered for variability checks
        #    varUse,=np.where((EGrayErr2[goodObs] > 0.0) &
        #                     (EGray[goodObs] != 0.0) &
        #                     (obsBandIndex[goodObs] == bandIndex))

            # which of these observations show high variability?
       #     isVar,=np.where(np.abs(EGray[goodObs[varUse]]/
       #                            np.sqrt(self.sigFgcm[bandIndex]**2. +
       #                                    EGrayErr2[goodObs[varUse]])) >
       #                     self.varNSig)
            # and flag these objects.  Note that each object may be listed multiple
            #  times but this only adds 1 to each uniquely
       #     varCount[goodStarsSub[varUse[isVar]]] += 1

        # make sure we have at least varMinBand bands detected
       # varStars,=np.where(varCount >= self.varMinBand)

       # objFlag[goodStars[varStars]] |= objFlagDict['VARIABLE']

        # first, we only use the required bands
        _,reqBandUse = esutil.numpy_util.match(self.fgcmStars.bandRequiredIndex,
                                               obsBandIndex[goodObs])

        # group by CCD and sum

        ## ccdGray = Sum(EGray/EGrayErr^2) / Sum(1./EGrayErr^2)
        ## ccdGrayRMS = Sqrt((Sum(EGray^2/EGrayErr^2) / Sum(1./EGrayErr^2)) - ccdGray^2)
        ## ccdGrayErr = Sqrt(1./Sum(1./EGrayErr^2))


        ccdGray[:,:] = 0.0
        ccdGrayRMS[:,:] = 0.0
        ccdGrayErr[:,:] = 0.0
        ccdNGoodObs[:,:] = 0
        ccdNGoodStars[:,:] = 0
        ccdNGoodTilings[:,:] = 0.0


        # temporary variable here
        ccdGrayWt = np.zeros_like(ccdGray)

        np.add.at(ccdGrayWt,
                  (obsExpIndex[goodObs[reqBandUse]],obsCCDIndex[goodObs[reqBandUse]]),
                  1./EGrayErr2GO[reqBandUse])
        np.add.at(ccdGray,
                  (obsExpIndex[goodObs[reqBandUse]],obsCCDIndex[goodObs[reqBandUse]]),
                  EGrayGO[reqBandUse]/EGrayErr2GO[reqBandUse])
        np.add.at(ccdGrayRMS,
                  (obsExpIndex[goodObs[reqBandUse]],obsCCDIndex[goodObs[reqBandUse]]),
                  EGrayGO[reqBandUse]**2./EGrayErr2GO[reqBandUse])
        np.add.at(ccdNGoodStars,
                  (obsExpIndex[goodObs[reqBandUse]],obsCCDIndex[goodObs[reqBandUse]]),
                  1)
        np.add.at(ccdNGoodObs,
                  (obsExpIndex[goodObs[reqBandUse]],obsCCDIndex[goodObs[reqBandUse]]),
                  objNGoodObs[obsObjIDIndex[goodObs[reqBandUse]],
                              obsBandIndex[goodObs[reqBandUse]]])

        # loop over the extra bands
        #  we only want to use previously determined "good" stars
        for extraBandIndex in self.fgcmStars.bandExtraIndex:
            extraBandUse, = np.where((obsBandIndex[goodObs] == extraBandIndex) &
                                     (objNGoodObs[obsObjIDIndex[goodObs],extraBandIndex] >=
                                      self.fgcmStars.minPerBand))

            np.add.at(ccdGrayWt,
                      (obsExpIndex[goodObs[extraBandUse]],obsCCDIndex[goodObs[extraBandUse]]),
                      1./EGrayErr2GO[extraBandUse])
            np.add.at(ccdGray,
                      (obsExpIndex[goodObs[extraBandUse]],obsCCDIndex[goodObs[extraBandUse]]),
                      EGrayGO[extraBandUse]/EGrayErr2GO[extraBandUse])
            np.add.at(ccdGrayRMS,
                      (obsExpIndex[goodObs[extraBandUse]],obsCCDIndex[goodObs[extraBandUse]]),
                      EGrayGO[extraBandUse]**2./EGrayErr2GO[extraBandUse])
            np.add.at(ccdNGoodStars,
                      (obsExpIndex[goodObs[extraBandUse]],obsCCDIndex[goodObs[extraBandUse]]),
                      1)
            np.add.at(ccdNGoodObs,
                      (obsExpIndex[goodObs[extraBandUse]],obsCCDIndex[goodObs[extraBandUse]]),
                      objNGoodObs[obsObjIDIndex[goodObs[extraBandUse]],
                                  obsBandIndex[goodObs[extraBandUse]]])


        # need at least 3 or else computation can blow up
        gd = np.where((ccdNGoodStars > 2) & (ccdGrayWt > 0.0) & (ccdGrayRMS > 0.0))
        ccdGray[gd] /= ccdGrayWt[gd]
        tempRMS2 = np.zeros_like(ccdGrayRMS)
        tempRMS2[gd] = (ccdGrayRMS[gd]/ccdGrayWt[gd]) - (ccdGray[gd]**2.)
        ok = np.where(tempRMS2 > 0.0)
        #ccdGrayRMS[gd] = np.sqrt((ccdGrayRMS[gd]/ccdGrayWt[gd]) - (ccdGray[gd]**2.))
        ccdGrayRMS[ok] = np.sqrt(tempRMS2[ok])
        ccdGrayErr[gd] = np.sqrt(1./ccdGrayWt[gd])

        self.fgcmLog.info('Computed CCDGray for %d CCDs' % (gd[0].size))

        # set illegalValue for totally bad CCDs
        bad = np.where((ccdNGoodStars <= 2) | (ccdGrayWt <= 0.0) | (tempRMS2 <= 0.0))
        ccdGray[bad] = self.illegalValue
        ccdGrayRMS[bad] = self.illegalValue
        ccdGrayErr[bad] = self.illegalValue

        # check for infinities -- these should not be here now that I fixed the weight check
        bad=np.where(~np.isfinite(ccdGrayRMS))
        ccdGrayRMS[bad] = self.illegalValue
        bad=np.where(~np.isfinite(ccdGrayErr))
        ccdGrayErr[bad] = self.illegalValue

        # and the ccdNGoodTilings...
        ccdNGoodTilings[gd] = (ccdNGoodObs[gd].astype(np.float64) /
                               ccdNGoodStars[gd].astype(np.float64))


        # group CCD by Exposure and Sum

        goodCCD = np.where((ccdNGoodStars >= self.minStarPerCCD) &
                           (ccdGrayErr > 0.0) &
                           (ccdGrayErr < self.maxCCDGrayErr))

        self.fgcmLog.info('For ExpGray, found %d good CCDs' %
                         (goodCCD[0].size))

        # note: goodCCD[0] refers to the expIndex, goodCCD[1] to the CCDIndex

        expGray[:] = 0.0
        expGrayRMS[:] = 0.0
        expGrayErr[:] = 0.0
        expNGoodStars[:] = 0
        expNGoodCCDs[:] = 0
        expNGoodTilings[:] = 0.0

        # temporary
        expGrayWt = np.zeros_like(expGray)

        np.add.at(expGrayWt,
                  goodCCD[0],
                  1./ccdGrayErr[goodCCD]**2.)
        np.add.at(expGray,
                  goodCCD[0],
                  ccdGray[goodCCD]/ccdGrayErr[goodCCD]**2.)
        np.add.at(expGrayRMS,
                  goodCCD[0],
                  ccdGray[goodCCD]**2./ccdGrayErr[goodCCD]**2.)
        np.add.at(expNGoodCCDs,
                  goodCCD[0],
                  1)
        np.add.at(expNGoodTilings,
                  goodCCD[0],
                  ccdNGoodTilings[goodCCD])
        np.add.at(expNGoodStars,
                  goodCCD[0],
                  ccdNGoodStars[goodCCD])

        # need at least 3 or else computation can blow up
        gd, = np.where(expNGoodCCDs > 2)
        expGray[gd] /= expGrayWt[gd]
        expGrayRMS[gd] = np.sqrt((expGrayRMS[gd]/expGrayWt[gd]) - (expGray[gd]**2.))
        expGrayErr[gd] = np.sqrt(1./expGrayWt[gd])
        expNGoodTilings[gd] /= expNGoodCCDs[gd]

        # set illegal value for non-measurements
        bad, = np.where(expNGoodCCDs <= 2)
        expGray[bad] = self.illegalValue
        expGrayRMS[bad] = self.illegalValue
        expGrayErr[bad] = self.illegalValue
        expNGoodTilings[bad] = self.illegalValue


        self.fgcmPars.compExpGray[:] = expGray
        self.fgcmPars.compVarGray[gd] = expGrayRMS[gd]**2.
        self.fgcmPars.compNGoodStarPerExp = expNGoodStars

        ##  per band we plot the expGray for photometric exposures...

        self.fgcmLog.info('ExpGray computed for %d exposures.' % (gd.size))
        self.fgcmLog.info('Computed CCDGray and ExpGray in %.2f seconds.' %
                         (time.time() - startTime))

        #if (not doPlots):
        #    return
        if (doPlots):
            self.makeExpGrayPlots()


    def makeExpGrayPlots(self):
        """
        """

        # arrays we need
        expNGoodStars = snmm.getArray(self.expNGoodStarsHandle)
        expGray = snmm.getArray(self.expGrayHandle)

        expUse,=np.where((self.fgcmPars.expFlag == 0) &
                         (expNGoodStars > self.minStarPerExp))

        for i in xrange(self.fgcmPars.nBands):
            inBand, = np.where(self.fgcmPars.expBandIndex[expUse] == i)

            if (inBand.size == 0) :
                continue

            # plot histograms of EXP^gray

            fig=plt.figure(1,figsize=(8,6))
            fig.clf()

            ax=fig.add_subplot(111)

            coeff = histoGauss(ax, expGray[expUse[inBand]])

            ax.tick_params(axis='both',which='major',labelsize=14)
            ax.locator_params(axis='x',nbins=5)

            text=r'$(%s)$' % (self.fgcmPars.bands[i]) + '\n' + \
                r'$\mathrm{Cycle\ %d}$' % (self.cycleNumber) + '\n' + \
                r'$\mu = %.5f$' % (coeff[1]) + '\n' + \
                r'$\sigma = %.4f$' % (coeff[2])

            ax.annotate(text,(0.95,0.93),xycoords='axes fraction',ha='right',va='top',fontsize=16)
            ax.set_xlabel(r'$\mathrm{EXP}^{\mathrm{gray}}$',fontsize=16)
            ax.set_ylabel(r'# of Exposures',fontsize=14)

            fig.savefig('%s/%s_expgray_%s.png' % (self.plotPath,
                                                  self.outfileBaseWithCycle,
                                                  self.fgcmPars.bands[i]))

            # plot EXP^gray as a function of secZenith (airmass)
            secZenith = 1./(np.sin(self.fgcmPars.expTelDec[expUse[inBand]]) *
                            self.fgcmPars.sinLatitude +
                            np.cos(self.fgcmPars.expTelDec[expUse[inBand]]) *
                            self.fgcmPars.cosLatitude *
                            np.cos(self.fgcmPars.expTelHA[expUse[inBand]]))

            # zoom in on 1<secZenith<1.5 for plotting
            ok,=np.where(secZenith < 1.5)

            fig=plt.figure(1,figsize=(8,6))
            fig.clf()

            ax=fig.add_subplot(111)

            ax.hexbin(secZenith[ok],expGray[expUse[inBand[ok]]],rasterized=True)

            text = r'$(%s)$' % (self.fgcmPars.bands[i])
            ax.annotate(text,(0.95,0.93),xycoords='axes fraction',ha='right',va='top',fontsize=16)

            ax.set_xlabel(r'$\mathrm{sec}(\mathrm{zd})$',fontsize=16)
            ax.set_ylabel(r'$\mathrm{EXP}^{\mathrm{gray}}$',fontsize=16)

            fig.savefig('%s/%s_airmass_expgray_%s.png' % (self.plotPath,
                                                          self.outfileBaseWithCycle,
                                                          self.fgcmPars.bands[i]))

            # plot EXP^gray as a function of UT

            fig=plt.figure(1,figsize=(8,6))
            fig.clf()

            ax=fig.add_subplot(111)

            ax.hexbin(self.fgcmPars.expDeltaUT[expUse[inBand]],
                      expGray[expUse[inBand]],
                      rasterized=True)
            ax.annotate(text,(0.95,0.93),xycoords='axes fraction',ha='right',va='top',fontsize=16)

            ax.set_xlabel(r'$\Delta \mathrm{UT}$',fontsize=16)
            ax.set_ylabel(r'$\mathrm{EXP}^{\mathrm{gray}}$',fontsize=16)

            fig.savefig('%s/%s_UT_expgray_%s.png' % (self.plotPath,
                                                     self.outfileBaseWithCycle,
                                                     self.fgcmPars.bands[i]))

        # and plot EXP^gray vs MJD for all bands for deep fields
        fig = plt.figure(1,figsize=(8,6))
        fig.clf()

        ax=fig.add_subplot(111)

        firstMJD = np.floor(np.min(self.fgcmPars.expMJD))

        deepUse,=np.where(self.fgcmPars.expDeepFlag[expUse] == 1)

        ax.plot(self.fgcmPars.expMJD[expUse[deepUse]] - firstMJD,
                expGray[expUse[deepUse]],'k.')
        ax.set_xlabel(r'$\mathrm{MJD}\ -\ %.0f$' % (firstMJD),fontsize=16)
        ax.set_ylabel(r'$\mathrm{EXP}^{\mathrm{gray}}$',fontsize=16)

        ax.set_title(r'$\mathrm{Deep Fields}$')

        fig.savefig('%s/%s_mjd_deep_expgray.png' % (self.plotPath,
                                                     self.outfileBaseWithCycle))

        # And plot correlations of EXP^gray between pairs of bands
        for ind in xrange(self.fgcmStars.bandRequiredIndex.size-1):
            bandIndex0 = self.fgcmStars.bandRequiredIndex[ind]
            bandIndex1 = self.fgcmStars.bandRequiredIndex[ind+1]

            use0, = np.where((self.fgcmPars.expBandIndex == bandIndex0) &
                             (self.fgcmPars.expFlag == 0) &
                             (expGray > self.illegalValue))
            use1, = np.where((self.fgcmPars.expBandIndex == bandIndex1) &
                             (self.fgcmPars.expFlag == 0) &
                             (expGray > self.illegalValue))

            if use0.size == 0 or use1.size == 0:
                self.fgcmLog.info('Could not find photometric exposures in bands %d or %d' % (bandIndex0, bandIndex1))
                continue

            matchInd = np.clip(np.searchsorted(self.fgcmPars.expMJD[use0],
                                               self.fgcmPars.expMJD[use1]),
                               0,
                               use0.size-1)

            ok,=np.where(np.abs(self.fgcmPars.expMJD[use0[matchInd]] -
                                self.fgcmPars.expMJD[use1]) < self.expGrayCheckDeltaT)

            if ok.size == 0:
                self.fgcmLog.info('Could not find any matched exposures between bands %s and %s within %.2f minutes' %
                                  (self.fgcmPars.bands[bandIndex0],
                                  self.fgcmPars.bands[bandIndex1],
                                  self.expGrayCheckDeltaT * 24 * 60))
                continue

            fig=plt.figure(1,figsize=(8,6))
            fig.clf()

            ax=fig.add_subplot(111)

            ax.hexbin(expGray[use0[matchInd[ok]]],
                      expGray[use1[ok]], bins='log')
            ax.set_xlabel('EXP_GRAY (%s)' % (self.fgcmPars.bands[bandIndex0]))
            ax.set_ylabel('EXP_GRAY (%s)' % (self.fgcmPars.bands[bandIndex1]))
            ax.plot([-0.01,0.01],[-0.01,0.01],'r--')

            fig.savefig('%s/%s_expgray_compare_%s_%s.png' % (self.plotPath,
                                                             self.outfileBaseWithCycle,
                                                             self.fgcmPars.bands[bandIndex0],
                                                             self.fgcmPars.bands[bandIndex1]))

    def computeExpGraySmooth(self):
        """
        """

        # make a placeholder
        expGraySmooth = np.zeros_like(self.fgcmPars.compExpGraySmooth)

        expGray = snmm.getArray(self.expGrayHandle)

        expGrayRaw = np.zeros_like(expGray)
        expGrayRaw[:] = expGray
        if self.applyExpGraySmooth:
            # unapply correction!
            # this seems to give the wrong sign at the end?
            expGrayRaw[:] = expGray - self.fgcmPars.compExpGraySmooth
            #expGrayRaw[:] = expGray + self.fgcmPars.compExpGraySmooth

        # arbitrarily choose the minimum number of exposures to smooth
        # FIXME: make this configurable
        minExpsToSmooth = 5

        # histogram over the nights...
        h, rev = esutil.stat.histogram(self.fgcmPars.expNightIndex, rev=True)

        # this 5 is ar
        gd, = np.where(h >= minExpsToSmooth)

        for i in xrange(gd.size):
            # all the exposures on a night
            i1a = rev[rev[gd[i]]:rev[gd[i]+1]]

            # at the moment, painfully loop over them
            # FIXME on the bands
            for j in xrange(i1a.size):
                use, = np.where(((self.fgcmPars.expBandIndex[i1a] == 0) |
                                 (self.fgcmPars.expBandIndex[i1a] == 1) |
                                 (self.fgcmPars.expBandIndex[i1a] == 2)) &
                                (self.fgcmPars.expFlag[i1a] == 0) &
                                (np.abs(self.fgcmPars.expMJD[i1a] -
                                        self.fgcmPars.expMJD[i1a[j]]) <
                                 self.expGraySmoothDeltaT))
                if (use.size >= minExpsToSmooth):
                    expGraySmooth[i1a[j]] = np.median(expGrayRaw[i1a[use]])



        # make a plot of old vs new... per band?  meh
        fig = plt.figure(figsize=(8,6))
        fig.clf()
        ax = fig.add_subplot(111)

        use,=np.where((self.fgcmPars.compExpGraySmooth != 0.0) |
                      (expGraySmooth != 0.0))

        if (use.size > 0):
            ax.hexbin(self.fgcmPars.compExpGraySmooth[use],
                      expGraySmooth[use], bins='log')
            plotRange = np.array([expGraySmooth[use].min(),
                                  expGraySmooth[use].max()])
            ax.plot(plotRange, plotRange, 'r--')
            ax.set_xlabel('EXP_GRAY_SMOOTH input')
            ax.set_ylabel('EXP_GRAY_SMOOTH output')

            fig.savefig('%s/%s_smoothexpgray_vs_smoothexpgray_in.png' % (self.plotPath,
                                                                     self.outfileBaseWithCycle))
        plt.close()

        # and store new one
        self.fgcmPars.compExpGraySmooth[:] = expGraySmooth
