from __future__ import print_function

import numpy as np
import os
import sys
import esutil
import glob
import healpy as hp

class FgcmMakeStars(object):
    """
    """
    def __init__(self,starConfig):
        self.starConfig = starConfig

        requiredKeys=['bandAlias','requiredBands',
                      'minPerBand','matchRadius',
                      'isolationRadius','densNSide',
                      'densMaxPerPixel','referenceBand',
                      'zpDefault','matchNSide']

        for key in requiredKeys:
            if (key not in starConfig):
                raise ValueError("required %s not in starConfig" % (key))

        self.objCat = None

        # Note that the order doesn't matter for the making of the stars
        self.filterNames = starConfig['bandAlias'].keys()

        # check that the requiredBands are there...
        for reqBand in starConfig['requiredBands']:
            found=False
            for filterName in self.filterNames:
                if (starConfig['bandAlias'][filterName][0] == reqBand):
                    found = True
                    break
            if not found:
                raise ValueError("requiredBand %s not in bandAlias!" % (reqBand))


    def runFromFits(self, clobber=False):
        """
        """

        if 'starfileBase' not in self.starConfig:
            raise ValueError("Required starfileBase not in starConfig")

        observationFile = self.starConfig['starfileBase']+'_observations.fits'

        if (not os.path.isfile(observationFile)):
            raise IOError("Could not find observationFile %s" % (observationFile))

        obsIndexFile = self.starConfig['starfileBase']+'_obs_index.fits'

        self.makeReferenceStarsFromFits(observationFile)
        self.makeMatchedStarsFromFits(observationFile, obsIndexFile, clobber=clobber)

    def makeReferenceStarsFromFits(self, observationFile):
        """
        """

        import fitsio

        fits = fitsio.FITS(observationFile)
        #w=fits[1].where('band == "%s"' % (self.starConfig['referenceBand']))
        fitsWhere = None
        for filterName in self.filterNames:
            if (self.starConfig['bandAlias'][filterName][0] == self.starConfig['referenceBand']):
                clause = '(filtername == "%s")' % (filterName)
                if fitsWhere is None
                    fitsWhere = clause
                else:
                    fitsWhere = fitsWhere + ' || ' + clause
        w=fits[1].where(fitsWhere)

        obsCat = fits[1].read(columns=['RA','DEC'],upper=True,rows=w)

        if ('brightStarFile' in self.starConfig):
            brightStarCat = fitsio.read(self.starConfig['brightStarFile'],ext=1,upper=True)

            brightStarRA = brightStarCat['RA']
            brightStarDec = brightStarCat['DEC']
            brightStarRadius = brightStarCat['RADIUS']

        else :
            brightStarRA = None
            brightStarDec = None
            brightStarRadius = None

        self.makeReferenceStars(obsCat['RA'], obsCat['DEC'], bandSelected=True,
                                brightStarRA = brightStarRA,
                                brightStarDec = brightStarDec,
                                brightStarRadius = brightStarRadius)

        fitsio.write(self.starConfig['starfileBase']+'_prepositions.fits',self.objCat,clobber=True)


    def makeMatchedStarsFromFits(self, observationFile, obsIndexFile, clobber=False):
        """
        """

        import fitsio

        if (not clobber):
            if (os.path.isfile(obsIndexFile)):
                print("Found %s " % (obsIndexFile))
                return


        obsCat = fitsio.read(observationFile, ext=1,
                             columns=['RA','DEC','FILTERNAME'])

        filterNameArray = np.core.defchararray.strip(obsCat['FILTERNAME'])

        self.makeMatchedStars(obsCat['RA'], obsCat['DEC'], filterNameArray)

        # and save the outputs...
        fits=fitsio.FITS(obsIndexFile, mode='rw', clobber=True)
        fits.create_table_hdu(data=self.objIndexCat, extname='POS')
        fits[1].write(self.objIndexCat)

        fits.create_table_hdu(data=self.obsIndexCat, extname='INDEX')
        fits[2].write(self.obsIndexCat)



    def makeReferenceStars(self, raArray, decArray, bandSelected=False,
                           filterNameArray=None, bandAlias=None,
                           brightStarRA=None, brightStarDec=None, brightStarRadius=None):
        """
        """

        # can we use the better smatch code?
        try:
            import smatch
            hasSmatch = True
            print("Good news!  smatch is available.")
        except:
            hasSmatch = False
            print("Bad news.  smatch not found.")

        if (raArray.size != decArray.size):
            raise ValueError("raArray, decArray must be same length.")

        if (not bandSelected):
            if (filterNameArray is None):
                raise ValueError("Must provide filterNameArray if bandSelected == False")
            if (filterNameArray.size != raArray.size):
                raise ValueError("filterNameArray must be same length as raArray")

            # down-select
            #use,=np.where(bandArray == self.starConfig['referenceBand'])
            #raArray = raArray[use]
            #decArray = decArray[use]

            # We select based on the aliased *band* not on the filter name
            useFlag = None
            for filterName in self.filterNames:
                if (self.starConfig['bandAlias'][filterName][0] == self.starConfig['referenceBand']):
                    if useFlag is None:
                        useFlag = (filterNameArray == filterName)
                    else:
                        useFlag |= (filterNameArray == filterName)

            raArray = raArray[useFlag]
            decArray = decArray[useFlag]

        if (brightStarRA is not None and brightStarDec is not None and
            brightStarRadius is not None):
            if (brightStarRA.size != brightStarDec.size or
                brightStarRA.size != brightStarRadius.size):
                raise ValueError("brightStarRA/Dec/Radius must have same length")
            cutBrightStars = True
        else:
            cutBrightStars = False

        print("Matching %s observations in the referenceBand catalog to itself" %
              (raArray.size))

        if (hasSmatch):
            # faster smatch...
            matches = smatch.match(raArray, decArray, self.starConfig['matchRadius']/3600.0,
                                   raArray, decArray, nside=self.starConfig['matchNSide'], maxmatch=0)

            i1 = matches['i1']
            i2 = matches['i2']
        else:
            # slower htm matching...
            htm = esutil.htm.HTM(11)

            matcher = esutil.htm.Matcher(11, raArray, decArray)
            matches = matcher.match(raArray, decArray,
                                    self.starConfig['matchRadius']/3600.0,
                                    maxmatch=0)

            i1 = matches[0]
            i2 = matches[1]


        fakeId = np.arange(raArray.size)
        hist,rev = esutil.stat.histogram(fakeId[i1],rev=True)

        if (hist.max() == 1):
            raise ValueError("No matches found!")

        maxObs = hist.max()

        # how many unique objects do we have?
        histTemp = hist.copy()
        count=0
        for j in xrange(histTemp.size):
            jj = fakeId[j]
            if (histTemp[jj] >= self.starConfig['minPerBand']):
                i1a=rev[rev[jj]:rev[jj+1]]
                histTemp[matches['i2'][i1a]] = 0
                count=count+1

        print("Found %d unique objects with >= %d observations in %s band." %
              (count, self.starConfig['minPerBand'], self.starConfig['referenceBand']))

        # make the object catalog
        dtype=[('FGCM_ID','i4'),
               ('RA','f8'),
               ('DEC','f8')]

        self.objCat = np.zeros(count,dtype=dtype)
        self.objCat['FGCM_ID'] = np.arange(count)+1

        # rotate.  This works for DES, but we have to think about optimizing this...
        raTemp = raArray.copy()

        hi,=np.where(raTemp > 180.0)
        if (hi.size > 0) :
            raTemp[hi] = raTemp[hi] - 360.0

        # compute mean ra/dec
        index = 0
        for j in xrange(hist.size):
            jj = fakeId[j]
            if (hist[jj] >= self.starConfig['minPerBand']):
                i1a=rev[rev[jj]:rev[jj+1]]
                starInd=i2[i1a]
                # make sure this doesn't get used again
                hist[starInd] = 0
                self.objCat['RA'][index] = np.sum(raTemp[starInd])/starInd.size
                self.objCat['DEC'][index] = np.sum(decArray[starInd])/starInd.size
                index = index+1

        # restore negative RAs
        lo,=np.where(self.objCat['RA'] < 0.0)
        if (lo.size > 0):
            self.objCat['RA'][lo] = self.objCat['RA'][lo] + 360.0

        if (cutBrightStars):
            print("Matching to bright stars for masking...")
            if (hasSmatch):
                # faster smatch...

                matches = smatch.match(brightStarRA, brightStarDec, brightStarRadius,
                                       self.objCat['RA'], self.objCat['DEC'], nside=self.starConfig['matchNSide'],
                                       maxmatch=0)
                i1=matches['i1']
                i2=matches['i2']
            else:
                # slower htm matching...
                htm = esutil.htm.HTM(11)

                matcher = esutil.htm.Matcher(10, brightStarRA, brightStarDec)
                matches = matcher.match(raArray, decArray, brightStarRadius,
                                        maxmatch=0)
                i1=matches[0]
                i2=matches[1]

            print("Cutting %d objects too near bright stars." % (i2.size))
            self.objCat = np.delete(self.objCat,i2)

        # and remove stars with near neighbors
        print("Matching stars to neighbors...")
        if (hasSmatch):
            # faster smatch...

            matches=smatch.match(self.objCat['RA'], self.objCat['DEC'],
                                 self.starConfig['isolationRadius']/3600.0,
                                 self.objCat['RA'], self.objCat['DEC'],
                                 nside=self.starConfig['matchNSide'], maxmatch=0)
            i1=matches['i1']
            i2=matches['i2']
        else:
            # slower htm matching...
            htm = esutil.htm.HTM(11)

            matcher = esutil.htm.Matcher(self.objCat['RA'], self.objCat['DEC'])
            matches = matcher.match(self.objCat['RA'], self.objCat['DEC'],
                                    self.starConfig['isolationRadius']/3600.0,
                                    maxmatch = 0)
            i1=matches[0]
            i2=matches[1]

        use,=np.where(i1 != i2)

        if (use.size > 0):
            neighbored = np.unique(i2[use])
            print("Cutting %d objects within %.2f arcsec of a neighbor" %
                  (neighbored.size, self.starConfig['isolationRadius']))
            self.objCat = np.delete(self.objCat, neighbored)

        # and we're done

    def makeMatchedStars(self, raArray, decArray, filterNameArray):
        """
        """

        if (self.objCat is None):
            raise ValueError("Must run makeReferenceStars first")

        # can we use the better smatch code?
        try:
            import smatch
            hasSmatch = True
        except:
            hasSmatch = False

        if (raArray.size != decArray.size or
            raArray.size != filterNameArray.size):
            raise ValueError("raArray, decArray, filterNameArray must be same length")

        # translate filterNameArray to bandArray ... can this be made faster, or
        #  does it need to be?
        bandArray = np.zeros_like(filterNameArray)
        for filterName in self.filterNames:
            use,=np.where(filterNameArray == filterName)
            bandArray[use] = self.starConfig['bandAlias'][filterName][0]


        print("Matching positions to observations...")

        if (hasSmatch):
            # faster smatch...

            matches=smatch.match(self.objCat['RA'], self.objCat['DEC'],
                                 self.starConfig['matchRadius']/3600.0,
                                 raArray, decArray,
                                 nside=self.starConfig['matchNSide'],
                                 maxmatch=0)
            i1=matches['i1']
            i2=matches['i2']
        else:
            # slower htm matching...
            htm = esutil.htm.HTM(11)

            matcher = esutil.htm.Matcher(11, self.objCat['RA'], self.objCat['DEC'])
            matches = matcher.match(raArray, decArray,
                                    self.starConfig['matchRadius']/3600.,
                                    maxmatch=0)
            i1 = matches[0]
            i2 = matches[1]

        print("Collating observations")
        nObsPerObj, obsInd = esutil.stat.histogram(i1, rev=True)

        if (nObsPerObj.size != self.objCat.size):
            raise ValueError("Number of reference stars does not match observations.")

        # which stars have at least minPerBand observations in each required band?
        #req, = np.where(np.array(self.starConfig['requiredFlag']) == 1)
        #reqBands = np.array(self.starConfig['bands'])[req]
        reqBands = np.array(self.starConfig['requiredBands'])

        # this could be made more efficient
        print("Computing number of observations per band")
        nObs = np.zeros((reqBands.size, self.objCat.size), dtype='i4')
        for i in xrange(reqBands.size):
            use,=np.where(bandArray[i2] == reqBands[i])
            hist = esutil.stat.histogram(i1[use], min=0, max=self.objCat.size-1)
            nObs[i,:] = hist


        # cut the star list to those with enough per band
        minObs = nObs.min(axis=0)

        # and our simple classifier
        #    1 is a good star, 0 is bad.
        objClass = np.zeros(self.objCat.size, dtype='i2')

        # make sure we have enough per band
        gd,=np.where(minObs >= self.starConfig['minPerBand'])
        objClass[gd] = 1
        print("There are %d stars with at least %d observations in each required band." %
              (gd.size, self.starConfig['minPerBand']))


        # cut the density of stars down with sampling.

        theta = (90.0 - self.objCat['DEC'][gd])*np.pi/180.
        phi = self.objCat['RA'][gd]*np.pi/180.

        ipring = hp.ang2pix(self.starConfig['densNSide'], theta, phi)
        hist, rev = esutil.stat.histogram(ipring, rev=True)

        high,=np.where(hist > self.starConfig['densMaxPerPixel'])
        ok,=np.where(hist > 0)
        print("There are %d/%d pixels with high stellar density" % (high.size, ok.size))
        for i in xrange(high.size):
            i1a=rev[rev[high[i]]:rev[high[i]+1]]
            cut=np.random.choice(i1a,size=i1a.size-self.starConfig['densMaxPerPixel'],replace=False)
            objClass[gd[cut]] = 0

        # redo the good object selection after sampling
        gd,=np.where(objClass == 1)

        # create the object catalog index
        self.objIndexCat = np.zeros(gd.size, dtype=[('FGCM_ID','i4'),
                                                    ('RA','f8'),
                                                    ('DEC','f8'),
                                                    ('OBSARRINDEX','i4'),
                                                    ('NOBS','i4')])
        self.objIndexCat['FGCM_ID'][:] = self.objCat['FGCM_ID'][gd]
        self.objIndexCat['RA'][:] = self.objCat['RA'][gd]
        self.objIndexCat['DEC'][:] = self.objCat['DEC'][gd]
        # this is the number of observations per object
        self.objIndexCat['NOBS'][:] = nObsPerObj[gd]
        # and the index is given by the cumulative sum
        self.objIndexCat['OBSARRINDEX'][1:] = np.cumsum(nObsPerObj[gd])[:-1]

        # and we need to create the observation indices from the OBSARRINDEX

        nTotObs = self.objIndexCat['OBSARRINDEX'][-1] + self.objIndexCat['NOBS'][-1]

        self.obsIndexCat = np.zeros(nTotObs,
                                    dtype=[('OBSINDEX','i4')])
        ctr = 0
        print("Spooling out %d observation indices." % (nTotObs))
        for i in gd:
            self.obsIndexCat[ctr:ctr+nObsPerObj[i]] = i2[obsInd[obsInd[i]:obsInd[i+1]]]
            ctr+=nObsPerObj[i]

        # and we're done




