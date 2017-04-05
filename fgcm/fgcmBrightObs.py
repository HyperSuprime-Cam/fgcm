from __future__ import print_function

import numpy as np
import fitsio
import os
import sys
import esutil
import time

from fgcmUtilities import _pickle_method
from fgcmUtilities import resourceUsage
from fgcmChisq import FgcmChisq

import types
import copy_reg

from sharedNumpyMemManager import SharedNumpyMemManager as snmm

copy_reg.pickle(types.MethodType, _pickle_method)


class FgcmBrightObs(object):
    """
    """
    ## FIXME:
    ##  I don't think this should run fgcmChisq

    def __init__(self,fgcmConfig,fgcmPars,fgcmStars,fgcmLUT):
        self.fgcmPars = fgcmPars
        self.fgcmLUT = fgcmLUT
        self.fgcmStars = fgcmStars

        self.brightObsGrayMax = fgcmConfig.brightObsGrayMax

        self.fgcmChisq = FgcmChisq(fgcmConfig,fgcmPars,fgcmStars,fgcmLUT)

        self.nCore = fgcmConfig.nCore

    def selectGoodStars(self,debug=False):
        """
        """

        ## FIXME: require this be previously run?
        parArray = fgcmPars.getParArray(fitterUnits=False)
        _ = self.fgcmChisq(parArray,fitterUnits=False,computeDerivatives=False,computeSEDSlopes=False)


        # create a link between the exposures and observations
        a,b=esutil.numpy_util.match(self.fgcmPars.expArray,
                                    snmm.getArray(self.fgcmStars.obsExpHandle)[:])
        self.obsExpIndexHandle = snmm.createArray(a.size,dtype='i4')
        snmm.getArray(self.obsExpIndexHandle)[b] = a

        # reset numbers
        snmm.getArray(self.fgcmStars.objMagStdMeanHandle)[:] = 99.0
        snmm.getArray(self.fgcmStars.objMagStdMeanErrHandle)[:] = 99.0

        # This operates on all stars...

        if (self.debug) :
            for i in xrange(self.fgcmStars.nStars):
                self._worker(i)

        else:
            pool = Pool(processes=self.nCore)
            pool.map(self._worker,np.arange(self.fgcmStars.nStars))
            pool.close()
            pool.join()

        # free shared arrays
        snmm.freeArray(self.obsExpIndexHandle)

    def _worker(self,objIndex):
        """
        """

        # make local pointers to useful arrays
        objMagStdMean = snmm.getArray(self.fgcmStars.objMagStdMeanHandle)
        #objMagStdMeanErr = snmm.getArray(self.fgcmStars.objMagStdMeanErrHandle)
        objNGoodObs = snmm.getArray(self.fgcmStars.objNGoodObsHandle)

        obsIndex = snmm.getArray(self.fgcmStars.obsIndexHandle)
        objObsIndex = snmm.getArray(self.fgcmStars.objObsIndexHandle)
        objNobs = snmm.getArray(self.fgcmStars.objNobsHandle)

        thisObsIndex = obsIndex[objObsIndex[objIndex]:objObsIndex[objIndex]+objNobs[objIndex]]
        thisObsExpIndex = snmm.getArray(self.obsExpIndexHandle)[thisObsIndex]

        # cut to good exposures
        #  I think this can be done in the parent more efficiently...but not now.
        gd,=np.where(self.fgcmPars.expFlag[thisObsExpIndex] == 0)

        thisObsIndex=thisObsIndex[gd]
        #thisObsExpIndex = thisObsExpIndex[gd]
        thisObsBandIndex = snmm.getArray(self.fgcmStars.obsBandIndexHandle)[thisObsIndex]

        obsMagStd = snmm.getArray(self.fgcmStars.obsMagStdHandle)

        # split out the filters (instead of loop of wheres)...
        h,rev=esutil.stat.histogram(obsBandIndex[thisObsIndex],rev=True,
                                    min=0,max=self.fgcmPars.nBands-1)

        for j in xrange(fgcmPars.nBands):
            if (h[j] == 0):
                objNGoodObs[i,j] = 0
                continue

            i1a=rev[rev[j]:rev[j+1]]

            # find the brightest observation
            minMag = np.amin(obsMagStd[thisObsIndex[i1a]])

            # and all the observations that are comparable
            brightObs,=np.where((obsMagStd[thisObsIndex[i1a]] - minMag) <= self.brightObsGrayMax)
            # number of good observations are these bright ones
            objNGoodObs[i,j] = brightObs.size

            # and compute straight, unweighted mean of bright Obs
            objMagStdMean[i,j] = np.sum(obsMagStd[thisObsIndex[i1a[brightObs]]]) / brightObs.size

        # and we're done
