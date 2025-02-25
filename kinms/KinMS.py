# coding: utf-8
"""
Kinematic modelling code KinMS.

Copyright (C) 2019, Timothy A. Davis, Nikki Zabel, James M. Dawson
E-mail: DavisT -at- cardiff.ac.uk, zabelnj -at- cardiff.ac.uk, dawsonj5 -at- cardiff.ac.uk
Updated versions of the software are available through github:
https://github.com/TimothyADavis/KinMSpy

If you have found this software useful for your research,
I would appreciate an acknowledgment to the use of the
"KINematic Molecular Simulation (KinMS) routines of Davis et al., (2013)".
[MNRAS, Volume 429, Issue 1, p.534-555]

This software is provided as is without any warranty whatsoever.
For details of permissions granted please see LICENCE.md
"""

#=============================================================================#
#/// IMPORT PACKAGES /////////////////////////////////////////////////////////#
#=============================================================================#

import numpy as np
import scipy.integrate
from scipy import interpolate
from astropy.io import fits
from astropy.nddata.utils import Cutout2D
from astropy.convolution import convolve_fft
from astropy.convolution import convolve
import warnings; warnings.filterwarnings("ignore")
from kinms.utils.KinMS_figures import KinMS_plotter


class KinMSError(Exception):
    """
    Generates errors under the flag 'KinMSError'.
    
    :class KinMSError:
        Instantiates the Exception error 'KinMSError', for warning the user of faults 
        and exceptions.
    """
    pass


#=============================================================================#
#/// START OF CLASS //////////////////////////////////////////////////////////#
#=============================================================================#

class KinMS:
        
    """
    :class KinMS:
        Main workhorse of KinMSpy, used to generate spectral cubes.
    """
    #=========================================================================#
    #/////////////////////////////////////////////////////////////////////////#
    #=========================================================================#

    def __init__(self, xs, ys, vs, cellSize, dv, beamSize, lsf_fwhm=None,
                  nSamps=None, seed=None, fixSeed=True,
                 cleanOut=False,  huge_beam=False, verbose=False):
        """       
        :param xs:
            (float or int) x-axis size for resultant cube (in arcseconds)
        :param ys:
            (float or int) y-axis size for resultant cube (in arcseconds)
        :param vs:
            (float or int) Velocity axis size for resultant cube (in km/s)
        :param cellSize:
            (float or int) Pixel size required (arcsec/pixel)
        :param dv:
            (float or int) Channel size in velocity direction (km/s/channel)
        :param beamSize:
            (float or int, or list or array of float or int) Scalar or three element list for size of convolving beam (in arcseconds). If a scalar then beam is
            assumed to be circular. If a list/array of length two. these are the sizes of the major and minor axes,
            and the position angle is assumed to be 0. If a list/array of length 3, the first 2 elements are the
            major and minor beam sizes, and the last the position angle (i.e. [bmaj, bmin, bpa]).
        :param nSamps: 
            (float or int) Optional, default value is 1e5.
            Number of cloudlets to use to create the model. Large numbers will reduce numerical noise (especially
            in large cubes), at the cost of increasing runtime.
        :param fixSeed:
            (bool) Whether to use a fixed (or random) seed (list of four integers).
        :param cleanOut: 
            (bool) Optional, default value is False.
            If True then do not convolve with the beam, and output the "clean components". Useful to create
            input for other simulation tools (e.g sim_observe in CASA).
        :param huge_beam: 
            (bool) Optional, default is False.
            If True then astropy's convolve_fft is used instead of convolve, which is faster for very large beams.
        :param verbose: 
            (bool) Optional, default is False.
            If True, messages are printed throughout the code.                       
        """
                 
                          
        self.xs = xs
        self.ys = ys
        self.vs = vs
        self.cellSize = cellSize
        self.dv = dv
        self.beamSize = beamSize
        self.lsf_fwhm = lsf_fwhm
        self.fixSeed = fixSeed
        
        if not fixSeed:
            self.seed = np.random.randint(1, 100)*np.array([1,3,5,9])
        else:
            if seed != None:
                self.seed = seed*np.array([100, 101, 102, 103], dtype='int')
            else:
                self.seed = np.array([100, 101, 102, 103], dtype='int')
            
        self.cleanOut = cleanOut
        self.huge_beam = huge_beam
        self.verbose = verbose        

        if not nSamps:
            self.nSamps = int(5e5)
        else:
            self.nSamps = int(nSamps)
        
        # Work out images sizes
        self.x_size = np.round(self.xs / self.cellSize).astype(int)
        self.y_size = np.round(self.ys / self.cellSize).astype(int)
        self.v_size = np.round(self.vs / self.dv).astype(int)    

        if not self.cleanOut:
            self.psf = self.makebeam(self.x_size, self.y_size, self.beamSize,cellSize=self.cellSize)
        else:
            self.psf=1

        if self.lsf_fwhm != None:
            self.lsf = self.makelsf(self.v_size, self.lsf_fwhm, dv=self.dv)
        else:
            self.lsf = None
        
        #draw random samples, so only has to be done once
        rng1 = np.random.RandomState(self.seed[0])
        rng2 = np.random.RandomState(self.seed[1])
        rng4 = np.random.RandomState(self.seed[3]) 
        self.randompick_r = rng1.random_sample(self.nSamps) # Draws random float samples in the range [0,1]
        self.randompick_phi = rng2.random_sample(self.nSamps) * 2 * np.pi  
        self.randompick_vdisp= rng4.randn(self.nSamps)
    #=========================================================================#
    #/////////////////////////////////////////////////////////////////////////#
    #=========================================================================#

    def print_variables(self):
        """
        If "verbose", prints a summary of parameters for the user's convenience.
        
        :return: 
            (string) formatted display of all parameters used in KinMS() initialisation
        """

        print("\n\n*** Hello and welcome to KinMSpy ***")

        default_dict = {}
        option_dict = {}

        print('_' * 37 + '\n \n' + 'Setting user defined variables to: \n')

        for k, v in self.__dict__.items():

            if isinstance(v, bool):
                option_dict[k] = v
            elif isinstance(v, (int, float)):
                if k == 'restFreq' and v == 230.542e9:
                    default_dict[k] = v
                elif k == 'nSamps' and v == int(5e5):
                    default_dict[k] = v
                elif v > 0:
                    print(k + ' = ' + str(v))       
                else:
                    default_dict[k] = v
            elif isinstance(v, np.ndarray):
                if len(v) == 1:
                    if v != 0:
                        if k == 'posAng':
                            print(k + ' = ' + str(v - 180))
                        else:
                            print(k + ' = ' + str(v)) 
                    else:
                        default_dict[k] = v
                elif len(v) == 0:
                    default_dict[k] = v
                else:
                    if (v != 0).all():
                        if k == 'seed' and v[0] == 100 and v[3] == 103:
                            default_dict[k] = v
                            continue
                        if len(v) > 5:
                            print(k + ' = user defined array of length ' + str(len(v)))
                        else:
                            print(k + ' = ' + str(v))
                    else:
                        default_dict[k] = v

        print('_' * 37 + '\n \n' + 'Setting default values to: \n')

        for k, v in default_dict.items():
            if isinstance(v, (int, float)):
                print(k + ' = ' + str(v))
            elif len(v) > 5:
                print(k + ' = default array of length ' + str(len(v)))
            else:
                print(k + ' = ' + str(v))

        print('_' * 37 + '\n \n' + 'Setting options to: \n')

        for k, v in option_dict.items():
            print(k + ' = ' + str(v))

        print('_' * 37 + '\n')

        return

    #=========================================================================#
    #/////////////////////////////////////////////////////////////////////////#
    #=========================================================================#

    def makebeam(self, xpixels, ypixels, beamSize, cellSize=1, cent=None):
        """
        Creates a psf with which one can convolve their cube based on the beam provided.
        
        :param xpixels:
                (float or int) Number of pixels in the x-axis
        :param ypixels:
                (float or int) Number of pixels in the y-axis
        :param beamSize:
                (float or int, or list or array of float or int) Scalar or three element list for size of convolving beam (in arcseconds). If a scalar then beam is
                assumed to be circular. If a list/array of length two. these are the sizes of the major and minor axes,
                and the position angle is assumed to be 0. If a list/array of length 3, the first 2 elements are the
                major and minor beam sizes, and the last the position angle (i.e. [bmaj, bmin, bpa]).
        :param cellSize:
                (float or int) Pixel size required (arcsec/pixel)
        :param cent: 
            (array or list of float or int) Optional, default value is [xpixels / 2, ypixels / 2].
                Central location of the beam in units of pixels.
        :return psf or trimmed_psf:
                (float array) psf required for convlution in self.model_cube(). trimmed_psf returned if self.huge_beam=False, 
                otherwise default return is the untrimmed psf.              
        """

        if not cent: cent = [int(xpixels / 2), int(ypixels / 2)]

        beamSize = np.array(beamSize)

        try:
            if len(beamSize) == 2:
                beamSize = np.append(beamSize, 0)
            if beamSize[1] > beamSize[0]:
                beamSize[1], beamSize[0] = beamSize[0], beamSize[1]
            if beamSize[2] >= 180:
                beamSize[2] -= 180
        except:
            beamSize = np.array([beamSize, beamSize, 0])

        st_dev = beamSize[0:2] / cellSize / 2.355

        rot = beamSize[2]

        if np.tan(np.radians(rot)) == 0:
            dirfac = 1
        else:
            dirfac = np.sign(np.tan(np.radians(rot)))

        x, y = np.indices((int(xpixels), int(ypixels)), dtype='float')

        x -= cent[0]
        y -= cent[1]

        a = (np.cos(np.radians(rot)) ** 2) / (2 * st_dev[1] ** 2) + (np.sin(np.radians(rot)) ** 2) / \
            (2 * (st_dev[0] ** 2))

        b = (dirfac * (np.sin(2 * np.radians(rot)) ** 2) / (4 * st_dev[1] ** 2)) + ((-1 * dirfac) * \
            (np.sin(2 * np.radians(rot)) ** 2) / (4 * st_dev[0] ** 2))

        c = (np.sin(np.radians(rot)) ** 2) / (2 * st_dev[1] ** 2) + (np.cos(np.radians(rot)) ** 2) / \
            (2 * st_dev[0] ** 2)

        psf = np.exp(-1 * (a * x ** 2 - 2 * b * (x * y) + c * y ** 2))

        ### Trim around high values in the psf, to speed up the convolution ###

        psf[psf < 1e-5] = 0  # set all kernel values that are very low to zero

        # sum the psf in the beam major axis
        if 45 < beamSize[2] < 135:
            flat = np.sum(psf, axis=1)
        else:
            flat = np.sum(psf, axis=0)

        idx = np.where(flat > 0)[0]  # find the location of the non-zero values of the psf
        
        newsize = (idx[-1] - idx[0])  # the size of the actual (non-zero) beam is this
        #
        if newsize % 2 == 0:
            newsize += 1  # add 1 pixel just in case
        else:
            newsize += 2  # if necessary to keep the kernel size odd, add 2 pixels
        
        if newsize>np.min([xpixels,ypixels]):
            if np.min([xpixels,ypixels]) % 2 == 0:
                newsize = np.min([xpixels,ypixels])-1  # keep the kernel size odd
            else:
                newsize = np.min([xpixels,ypixels])  
                
                
        trimmed_psf = Cutout2D(psf, (cent[1], cent[0]), newsize).data  # cut around the psf in the right location

        return trimmed_psf
    
    
    def makelsf(self, vpixels, lsf_width, dv=1, lsfcent=None):
        """
        T.Tsukui 2023/04/10
        Creates a line spread function (LSF) with which one can convolve their cube.
        
        :param vpixels:
                (float or int) Number of pixels in the v-axis
        :param lsf_width:
                (float or int) Scalar for width of convolving LSF (in km/s).
        :param dv:
                (float or int) spectral gridding size required (km/s/pixel)
        :param lsfcent: 
            (array or list of float or int) Optional, default value is vpixel/2.
                Central location of the beam in units of pixels.
        :return lsf:
                (float array) lsf required for convlution in self.model_cube().  
        """

        if not lsfcent: lsfcent = int(vpixels / 2)

        x = np.arange(vpixels) - lsfcent

        lsf = np.exp(-0.5 * (x / (lsf_width/dv/2.355)) ** 2)

        lsf[lsf < 1e-5] = 0  # set all kernel values that are very low to zero
        lsf/=np.sum(lsf) # normalise the lsf

        idx = np.where(lsf > 0)[0]  # find the location of the non-zero values of the psf

        newsize = (idx[-1] - idx[0])  # the size of the actual (non-zero) beam is this

        if newsize % 2 == 0:
            newsize += 1  # add 1 pixel just in case
        else:
            newsize += 2  # if necessary to keep the kernel size odd, add 2 pixels
        
        if newsize>vpixels:
            if vpixels % 2 == 0:
                newsize = vpixels-1  # keep the kernel size odd
            else:
                newsize = vpixels 

        return lsf[lsfcent-newsize//2:lsfcent+newsize//2+1]

    #=========================================================================#
    #/////////////////////////////////////////////////////////////////////////#
    #=========================================================================#   
        
    def kinms_sampleFromArbDist_oneSided(self, sbRad, sbProf, nSamps, diskThick):
        """
        Samples cloudlets from radial profiles provided given that inClouds is not provided in the __init__. 
        
        :param sbRad:
                (numpy array) Radius vector for surface brightness profile (units of arcseconds).
        :param sbProf: 
                (numpy array) Surface brightness profile (arbitrarily scaled) as a function of 'sbrad'.
        :param nSamps: 
                (int) Number of cloudlets to use to create the model. Large numbers will reduce numerical noise (especially
                in large cubes), at the cost of increasing runtime.
        :param diskThick: 
                (numpy array) The disc scaleheight in arcseconds. If a single value then this is used at all radii. If an array/list
                then it should have the same length as 'sbrad', and will be the disc thickness as a function of that.
        :return inClouds:
            (numpy array) 3 dimensional array of cloudlet positions within the cube initialised by KinMS().
        """
        if self.verbose: 
            print('Generating cloudlets,', end =' ')


        
        # Randomly generate the radii of clouds based on the distribution given by the brightness profile.
        px = scipy.integrate.cumtrapz(sbProf * 2 * np.pi * abs(sbRad), abs(sbRad), initial=0) #  Integrates the surface brightness profile
        px /= max(px) # Normalised integral of the surface brightness profile
        
        r_flat = np.interp(self.randompick_r,px,sbRad)
        
        # Generates a random phase around the galaxy's axis for each cloud.
        
        phi = self.randompick_phi

        
        # Find the thickness of the disk at the radius of each cloud, and generates a random (uniform) z-position satisfying |z|<disk_here.
        if np.any(diskThick != 0):
            if len(diskThick) > 1 and len(diskThick) != len(sbRad):
                raise KinMSError('\n \n ... Please make sure the length of diskThick is the same as that of sbRad!')

            elif len(diskThick) > 1:
                diskThick = np.array(diskThick)
                diskThick_here = np.interp(r_flat,sbRad, diskThick)
                if self.verbose: print('Using the scale height profile provided.')
            else:
                diskThick_here = diskThick
                if self.verbose: print('Using an exponential scale height of ' + str(diskThick) + '.')
            rng3 = np.random.RandomState(self.seed[2])
            z_pos = diskThick_here * rng3.exponential(1,nSamps)*rng3.choice([-1,1],size=nSamps)
        else:
            if self.verbose: print('Using a thin disc assumption.')
            z_pos = 0
        

        # Calculate the x & y position of the clouds in the x-y plane of the disk.
        r_3d = np.sqrt(r_flat ** 2 + z_pos ** 2)
        sintheta=np.sqrt(1-(z_pos / r_3d)**2)
        x_pos = r_3d * np.cos(phi) * sintheta
        y_pos = r_3d * np.sin(phi) * sintheta

        # Generates the output array
        inClouds = np.empty((nSamps, 3))
        inClouds[:, 0] = x_pos
        inClouds[:, 1] = y_pos
        inClouds[:, 2] = z_pos
        
        return inClouds

    #=========================================================================#
    #/////////////////////////////////////////////////////////////////////////#
    #=========================================================================#
    
    def kinms_create_velField_oneSided(self, velRad, posAng_rad=None, inc_rad=None):
        """
        Creates an array of line-of-sight velocities, accounting for velocity dispersion and projection.
        
        :param velRad:
            (numpy array) Radius vector for velocity profile (units of arcseconds).
        :param posAng_rad: 
            (float or int, or array of float or int) Optional, default value is None.
            Position angle (PA) of the disc (a PA of zero means that the redshifted part of the cube is aligned
            with the positive y-axis). If single valued then the disc major axis is straight. If an array is passed
            then it should describe how the position angle changes as a function of `velrad` (so this can be used
            to create position angle warps).
        :param inc_rad: 
            (float or int, or array of float or int) Optional, default value is None.
            Inclination angle of the gas disc on the sky (degrees). Can input a constant or a vector, giving the
            inclination as a function of the radius vector 'velrad' (in order to model warps etc).
        :return los_vel:
            (numpy array) Line-of-sight velocities for projected particles positioned by velRad.
        """
        
        if np.any(self.vPhaseCent != [0,0]):
            r_flatv = np.sqrt((self.x_pos - self.vPhaseCent[0]) ** 2 + (self.y_pos - self.vPhaseCent[1]) ** 2)
        else:
            r_flatv = self.r_flat
        
                                                                
        vRad = np.interp(r_flatv, velRad, self.velProf)  # Evaluate the velocity profile at the sampled radii

        # Calculate a peculiar velocity for each cloudlet based on the velocity dispersion
        if self.inClouds_given:
            velDisp=self.randompick_vdisp[0:self.nSamps].copy()
        else:
            velDisp = self.randompick_vdisp.copy()
        if len(self.gasSigma) > 1:
            velDisp *=  np.interp(r_flatv, velRad, self.gasSigma)
        else:
            velDisp *= self.gasSigma
        

        # Find the rotation angle so the velocity field has the correct position angle (allows warps)

        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#       
        #~~~   REMOVAL OF POSITION ANGLE OFFSET BETWEEN SBPROF AND VELPROF  ~~#
        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~# 

        if len(self.vPosAng)==0:
            vPosAng_rad = posAng_rad

        elif len(self.vPosAng) == 1:
            vPosAng_rad =self.vPosAng

        elif len(self.vPosAng) > 1:
            vPosAng_rad = np.interp(r_flatv, velRad, self.vPosAng)



        theta=np.arctan2((self.y_pos - self.vPhaseCent[1]),(self.x_pos - self.vPhaseCent[0])) + (np.radians(posAng_rad - vPosAng_rad))

        #Calculate the los velocity for each cloudlet                                                                                                          
        los_vel = velDisp + ((-1) * vRad * (np.cos(theta) * np.sin(np.radians(inc_rad))))

        
        # add a radial velocity component if needed            
        if callable(self.radial_motion_func):
            los_vel+=self.radial_motion_func(r_flatv*self.cellSize,theta,inc_rad)

                    
        # Output the array of los velocities
        return los_vel
        
    def save_fits(self, cube, cent):
        """
        Outputs a .fits file containing the datacube and relevant header information.
        
        :param cube:
            (numpy array) 3 dimensional spectral cube required for saving to .fits file
        :param cent:
            (numpy array of intigers) Location of the central x and y positions (in units of pixels),
            and index of the central velocity channel.
        :return:
            None
        """

        hdu = fits.PrimaryHDU(cube.T)
        hdu.header['CDELT1'] = (self.cellSize / -3600)
        hdu.header['CDELT2'] = (self.cellSize / 3600)
        hdu.header['CDELT3'] = (self.dv * 1000.)
        hdu.header['CRPIX1'] = (self.x_size//2) + 1#(cent[0] + 1)
        hdu.header['CRPIX2'] = (self.y_size//2) + 1#(cent[1] + 1)
        hdu.header['CRPIX3'] = 1
        hdu.header['CRVAL1'] = (self.ra) or 0.0 
        hdu.header['CRVAL2'] = (self.dec) or 0.0
        hdu.header['CRVAL3'] = ((self.vSys-self.dv*(cent[2]-0.5)) * 1000.), 'm/s'
        hdu.header['CUNIT1'] = 'deg'
        hdu.header['CUNIT2'] = 'deg'
        hdu.header['CUNIT3'] = 'm/s     '
        hdu.header['BSCALE'] = 1.0
        hdu.header['BZERO'] = 0.0
        hdu.header['BMIN'] = (self.beamSize[1] / 3600)
        hdu.header['BMAJ'] = (self.beamSize[0] / 3600)
        hdu.header['BTYPE'] = 'Intensity'
        hdu.header['BPA'] = (self.beamSize[2])
        hdu.header['CTYPE1'] = 'RA---SIN'
        hdu.header['CTYPE2'] = 'DEC--SIN'
        hdu.header['CTYPE3'] = 'VRAD    ' 
        hdu.header['EQUINOX'] = 2000.
        hdu.header['RADESYS'] = 'FK5'
        hdu.header['BUNIT'] = self.bunit
        hdu.header['SPECSYS'] = 'BARYCENT'
        hdu.header['RESTFRQ'] = self.restFreq

        hdu.writeto(self.fileName + '_simcube.fits', overwrite=True, output_verify='fix')

        return                
                
                 
    def gasGravity_velocity(self, x_pos, y_pos, z_pos, massDist, velRad):
       """
       Calculates an array of line-of-sight velocity alterations, accounting for the effects 
       of the mass of gas in the disk (in this case assuming spherical symmetry).
       
       :param x_pos:
           (numpy array) X position of each cloudlet. Units of arcseconds.
       :param y_pos:
           (numpy array) Y position of each cloudlet. Units of arcseconds.
       :param z_pos:
           (numpy array) Z position of each cloudlet. Units of arcseconds.
       :param massDist:
           (numpy array) Array of ([gasmass,distance]) - total gas mass in solar masses, total distance in Mpc.
       :param velRad:
           (numpy array) Radius vector for cloudlets (in units of pixels).
       :return add_to_circ_vel:
           (numpy array) Additions to the circular velocity due to the internal mass of the gas, in units of km/s.
       """

       if not len(massDist) == 2:
           raise KinMSError('\n Please provide "massDist" as a list of [gasmass, distance] - total gas mass in solar masses, total distance in Mpc.')

       grav_const = 4.301e-3  # g in solar masses, pc, and km/s
       arcsec_to_pc = 4.84  # Angular distance in arcsec to physical distance in pc, when seen at distance D in Mpc
       
       rad = np.sqrt((x_pos ** 2) + (y_pos ** 2) + (z_pos ** 2))  # 3D radius
       

       cumMass = (np.arange(x_pos.size + 1)) * (massDist[0] / x_pos.size)  # Cumulative mass

       max_velRad = np.max(velRad).clip(min=np.max(rad), max=None) + 1  # The max vel_Rad clipped to above the minimum rad
       new_rad = np.insert(sorted(rad), 0, 0)  # sorts rad and puts a 0 value at the start of it

       add_to_circ_vel_sqr = ((grav_const * np.interp(velRad,new_rad, cumMass)) / (arcsec_to_pc * velRad * massDist[1]))
       add_to_circ_vel_sqr[~np.isfinite(add_to_circ_vel_sqr)] = 0

       return add_to_circ_vel_sqr         
       
       
    #=========================================================================#
    #~~~~~~~~~~~~~~~~~~~~~~~~~~~HELP FUNCTIONS~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#
    #=========================================================================#

    def generate_cloudlets(self):
        """
        A helper function for generating cloudlets by running kinms_sampleFromArbDist_oneSided. Raises
        a KinMSError if generate_cloudlets is called but sbRad and sbProf are not set.
        
        :return:
            None
        """

        if not len(self.sbRad) or not len(self.sbProf):
            raise KinMSError('\n Please define either \"inClouds\" or \"sbRad\" and \"sbProf\"')
        elif not len(self.sbRad) == len(self.sbProf):
            raise KinMSError('\n Please make sure "sbProf" and "sbRad" have the same length.')
        else:
            self.inClouds_given = False
            self.inClouds = self.kinms_sampleFromArbDist_oneSided(self.sbRad, self.sbProf, self.nSamps,self.diskThick)
                                                                  
    def set_cloud_positions(self):
        """
        Calculate and return the positions and velocities of the cloudlets in inClouds,
        and the radial distance in the x and y plane.
        
        :return:
            None
        """

        self.x_pos = (self.inClouds[:, 0] / self.cellSize)
        self.y_pos = (self.inClouds[:, 1] / self.cellSize)
        self.z_pos = (self.inClouds[:, 2] / self.cellSize)
        self.r_flat = np.sqrt(self.x_pos ** 2 + self.y_pos ** 2)
        
        
    def create_warp(self, array, r_flat):
        """
        If the array provided has a length > 1, create a warp. If it's a single value, create a flat profile.
        
        :param array: 
            (ndarray) array containing the radial profile
        :param r_flat: 
            (ndarray) Radius of each cloudlet from the kinematic centre in the plane of the disc (units of pixels)
        :return: 
            ndarray with the radial profile of the disc
        """

        if len(array) > 1:
            if not len(self.sbRad) == len(self.velRad):
                raise KinMSError('\n If you want to create a warp, please make sure "sbRad" and "velRad" have the same length.')
            radial_profile = np.interp(r_flat * self.cellSize,self.velRad, array)

        else:
            radial_profile = np.full(len(r_flat), array)

        return radial_profile

    #=========================================================================#
    #/////////////////////////////////////////////////////////////////////////#
    #=========================================================================#
            
    def inclination_projection(self, ang, x1, y1, z1):
        """
        Apply the projection as a result of inclination to the cloudlets.
        
        :param ang: 
            (float) inclination angle (in degrees)
        :param x1: 
            (ndarray) x-positions of the cloudlets
        :param y1: 
            (ndarray) y-positions of the cloudlets
        :param z1: 
            (ndarray) z-positions of the cloudlets
        :return: 
            x-, y-, and z-positions of the projected cloudlets
        """

        c = np.cos(np.radians(ang))
        s = np.sin(np.radians(ang))
        x2 = x1
        y2 = (c * y1) + (s * z1)
        z2 = (-s * y1) + (c * z1)

        return x2, y2, z2

    #=========================================================================#
    #/////////////////////////////////////////////////////////////////////////#
    #=========================================================================#
        

    def position_angle_rotation(self, ang, x2, y2, z2):
        """
        Apply the projection as a result of the position angle to the cloudlets.
        
        :param ang: 
            (float) position angle (in degrees)
        :param x2: 
            (ndarray) x-positions of the cloudlets
        :param y2: 
            (ndarray) y-positions of the cloudlets
        :param z2: 
            (ndarray) z-positions of the cloudlets
        :return: 
            x-, y-, and z-positions of the projected cloudlets
        """

        c = np.cos(np.radians(90-ang))
        s = np.sin(np.radians(90-ang))
        x3 = (c * x2) + (s * y2)
        y3 = (-s * x2) + (c * y2)
        z3 = z2

        return x3, y3, z3              

    #=========================================================================#
    #/////////////////////////////////////////////////////////////////////////#
    #=========================================================================#

    def set_cloud_velocities(self):
        """
        Find the los velocity and cube position of the clouds. If los velocity specified, 
        assume that the clouds have already been projected correctly.
        
        :return: 
            arrays with the x-, y-, and z- positions of the cloudlets, and their los velocities
        """
        if len(self.vLOS_clouds):
            los_vel = self.vLOS_clouds
            x3 = self.x_pos
            y3 = self.y_pos
            z3 = self.z_pos

        # If los velocities not specified, calculate them.
        # Include the potential of the gas.
        elif not len(self.velProf):
            raise KinMSError('\nPlease define either \"vLOS_clouds\" or \"velRad\" and \"velProf\".')

        else:
            # If velRad is not defined but sbRad is, set velRad to sbRad
            if not len(self.velRad) and len(self.sbRad):
                self.velRad = self.sbRad

            if len(self.massDist) > 1:
                gasGravVel_sqr = self.gasGravity_velocity(self.x_pos * self.cellSize, self.y_pos * self.cellSize, self.z_pos * self.cellSize, self.massDist, self.velRad)
                self.velProf = np.sqrt((self.velProf ** 2) + (gasGravVel_sqr))
                
            
            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#
            # ~~~   CREATION OF POSITION ANGLE/INCLINATION  WARPS IN THE DISK ~~~~~#
            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#

            if len(self.posAng) > 1:
                if not len(self.posAng) == len(self.velRad):
                    print(self.posAng, len(self.posAng))
                    raise KinMSError('Please make sure \'posAng\' is either a single value, or has the same length as \'velRad\'.')

            posAng_rad = self.create_warp(self.posAng, self.r_flat)
            
            
            inc_rad = self.create_warp(self.inc, self.r_flat)


            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#
            # ~~~   CREATION OF LOS VELOCITIES IF NOT PROVIDED  ~~~~~~~~~~~~~~~~~~~#
            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#

            los_vel = self.kinms_create_velField_oneSided((self.velRad / self.cellSize), posAng_rad=posAng_rad, inc_rad=inc_rad)

            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#
            # ~~~   PROJECT CLOUDS IN POSITION ANGLE AND INCLINATION   ~~~~~~~~~~~~#
            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#
            

            x2, y2, z2 = self.inclination_projection(inc_rad, self.x_pos, self.y_pos, self.z_pos)
            

            x3, y3, z3 = self.position_angle_rotation(posAng_rad, x2, y2, z2)
            

            
        return x3, y3, z3, los_vel
        
    # =========================================================================#
    # /////////////////////////////////////////////////////////////////////////#
    # =========================================================================#

    def find_clouds_in_cube(self, los_vel, cent, x2, y2):
        """
        Returns the clouds that lie inside the cube.
        
        :param los_vel: 
            (ndarray) contains the line of sight velocities of each cloudlet, in km/s.
        :param cent: 
            (ndarray of length 2) contains the x and y coordinates of the centre of the object within the cube
        :param x2: 
            (ndarray) x-positions of the cloudlets within the cube
        :param y2: 
            (ndarray) y-positions of the cloudlets within the cube
        :return: 
            arrays with the positions of the cloudlets within the cube, and the indices of these positions
        """

        
        # Centre the clouds in the cube on the centre of the object.
        los_vel_dv_cent2 = np.round((los_vel / self.dv) + cent[2])
        x2_cent0 = np.round(x2 + cent[0])
        y2_cent1 = np.round(y2 + cent[1])

        # Find the reduced set of clouds that lie inside the cube.
        subs = (((x2_cent0 >= 0) & (x2_cent0 < self.x_size) & (y2_cent1 >= 0) & (y2_cent1 < self.y_size) & \
                         (los_vel_dv_cent2 >= 0) & (los_vel_dv_cent2 < self.v_size)))

        clouds2do = np.empty((np.sum(subs), 3))
        clouds2do[:, 0] = x2_cent0[subs]
        clouds2do[:, 1] = y2_cent1[subs]
        clouds2do[:, 2] = los_vel_dv_cent2[subs]

        return clouds2do, subs
    
    def histo_with_bincount(self,vals,bins):
        """
        bincount is subtantially faster than histogramdd unless you need weights
    
        ; param vals:
            (ndarray) contains the x-, y-, and v-positions of the cloudslets in the cube in units of pixels
        ; param bins
            (ndarray) the number of pixels in x, y and v
        ; return:
            (ndarray) 3D datacube (unnormalised)
        """
        cd = vals[:,2]
        cd += bins[2]*(vals[:,1])
        cd += (bins[2]*bins[1])*(vals[:,0])
        return np.bincount(cd.astype(int), minlength=np.product(bins)).reshape(*bins).astype(np.float64)
            
    def add_fluxes(self, clouds2do, subs):
        """
        If there are clouds to use, and we know the flux of each cloud, add them to the cube.
        If not, bin each position to get a relative flux.
        
        :param clouds2do: 
            (ndarray) contains the x-, y-, and v-positions of the cloudslets in the cube
        :param subs: 
            (ndarray) the cloudlets to add to the cube
        :return: 
            spectral cube with fluxes added to the cloudlets
        """

        nsubs=subs.sum()
        if nsubs > 0:

            if np.any(self.flux_clouds) != None:

                if not self.inClouds_given:
                    raise KinMSError('\n\"flux_clouds\" can only be used in combination with \"inClouds\". '
                          'Please specify \"inClouds\" if you would like to define \"flux_clouds\".')

                if not (len(self.flux_clouds.shape) == 1 and len(self.flux_clouds) == max(self.inClouds.shape)):
                    raise KinMSError('\nPlease make sure \"flux_clouds\" is a 1D array matching the length of \"inClouds\".')

                #cube = np.zeros((int(x_size), int(y_size), int(v_size)))
                
                cube, edges = np.histogramdd(clouds2do, bins=(self.x_size, self.y_size, self.v_size),
                                                 range=((0, self.x_size), (0, self.y_size), (0, self.v_size)),weights=self.flux_clouds[subs])                                 
                    
            else:
                cube = self.histo_with_bincount(clouds2do,bins=np.array([self.x_size, self.y_size, self.v_size]))
                #cube, edges =np.histogramdd(clouds2do, bins=(x_size, y_size, v_size),range=((0, x_size), (0, y_size), (0, v_size)))

        else:
            cube = np.zeros((int(self.x_size), int(self.y_size), int(self.v_size)))

        return cube
        
    # =========================================================================#
    # /////////////////////////////////////////////////////////////////////////#
    # =========================================================================#

    def normalise_cube(self, cube, psf):
        """
        Normalise cube by the known integrated flux.
        
        :param cube: 
            (3D array) unnormalised spectral cube
        :param psf: 
            (2D array) psf of the mock observations, to convolve the cube with
        :param lsf: 
            (1D array) lfs of the mock observations, to convolve the cube with
        """

        if self.intFlux > 0:
            if not self.cleanOut:
                cube *= ((self.intFlux * psf.sum()) / (cube.sum() * self.dv))
            else:
                cube *= (self.intFlux / (cube.sum() * self.dv))

        elif np.any(self.flux_clouds) != None:
            cube = cube
            #cube *= (self.flux_clouds.sum() / cube.sum())
            #to preserve the flux distribution described by flux_clouds
            #the original code artificially increase the flux, compensating the lost flux due to convolution and out of range of the particle's velocity .

        else:
            cube /= cube.sum()

        return cube       
        
    def model_cube(self,inc, posAng, gasSigma=0, diskThick=0, flux_clouds=None, 
                 sbProf=[], sbRad=[], velRad=[], velProf=[], inClouds=[], vLOS_clouds=[], massDist=[], radial_motion_func=None, intFlux=None, phaseCent=[0,0], vOffset=0,
                 vPosAng=[], vPhaseCent=[0,0],returnClouds=False, toplot=False,fileName='',vSys=0,bunit='Jy/beam', ra=None, dec=None,restFreq=None,**kwargs):
        """
        Do the actual modelling of the spectral cube
        
        :param inc:
            (float or int, or list or array of float or int) Inclination angle of the gas disc on the sky (degrees). Can input a constant or a vector, giving the
            inclination as a function of the radius vector 'velrad' (in order to model warps etc).
        :param posAng:
            (float or int, or list or array of float or int) Position angle (PA) of the disc (a PA of zero means that the redshifted part of the cube is aligned
            with the positive y-axis). If single valued then the disc major axis is straight. If an array is passed
            then it should describe how the position angle changes as a function of `velrad` (so this can be used
            to create position angle warps).
        :param gasSigma: 
            (float or int, or array or list of float or int) Optional, default is value 0.
            Velocity dispersion of the gas (units of km/s). If single valued then the velocity dispersion is
            constant throughout the disc. If an array/list is passed then it should describe how the velocity
            dispersion changes as a function of 'velrad'.
        :param diskThick: 
            (float or int, or array or list of float or int) Optional, default value is 0.
            The disc scaleheight in arcseconds. If a single value then this is used at all radii. If an array/list
            then it should have the same length as 'sbrad', and will be the disc thickness as a function of that.
        :param flux_clouds: 
            (array or list of float or int) Optional, default value is 0.
            This vector can be used to supply the flux of each point in 'inclouds'. If used alone then total flux
            in the model is equal to total(flux_inclouds). If 'intflux' used then this vector denotes the relative
            brightness of the points in 'inclouds'.
        :param sbProf: 
            (array or list of float or int) Optional, default value is [].
            Surface brightness profile (arbitrarily scaled) as a function of 'sbrad'.
        :param sbRad: 
            (array or list of float or int) Optional, default value is [].
            Radius vector for surface brightness profile (units of arcseconds).
        :param velRad: 
            (array or list of float or int) Optional, defaults to 'sbRad'.
            Radius vector for velocity profile (units of arcseconds).
        :param velProf: 
            (array or list of float or int) Optional, default value is [].
            Circular velocity profile (in km/s) as a function of 'velrad'.
        :param inClouds: 
            (array or list of float or int) Optional, default value is [].
            If your required gas distribution is not symmetric, you may input vectors containing the position of the
            clouds you wish to simulate. This 3-vector should contain the x, y and z positions, in units of
            arcseconds from the phase centre. If this variable is used, then 'diskthick', 'sbrad' and 'sbprof' are
            ignored. Example: inclouds = [[0,0,0], [10,-10,2], ..., [xpos, ypos, zpos]].
        :param vLOS_clouds: 
            (array or list of float or int) Optional, default value is [].
            This vector should contain the LOS velocity for each point defined in 'inclouds', in units of km/s. If
            not supplied then 'inclouds' is assumed to be the -face on- distribution and that 'velprof' or 'velrad'
            should be used, and the distribution projected. If this variable is used then 'gassigma' and 'inc'
            are ignored.
        :param massDist: 
            (list of float) Optional, default value is [].
            List of [gasmass, distance] - total gas mass in solar masses, total distance in Mpc.                 
        :param intFlux: 
            (float) Optional, default value is 1.
            Total integrated flux you want the output gas to have. (In units of BUNIT - default Jy/(km/s).
        :param phaseCent: 
            (list or array of float or int of length 2) Optional, default value is [0, 0].
            Specifies the morphological centre of the disc structure you create with respect to the central pixel
            of the generated cube.
        :param vOffset: 
            (float or int) Optional, default value is 0.
            Offset from the centre of the velocity axis in km/s.
        :param vPosAng: 
            (float or int, or array or list of float or int) Optional, default value is 0.
            Kinematic position angle of the disc, using the usual astronomical convention. If single valued then the
            disc kinematic major axis is straight. If an array is passed then it should describe how the kinematic
            position angle changes as a function of 'velrad'. Used if the kinematic and morphological position
            angles are not the same.
        :param vPhaseCent: 
            (list of float or int of length 2) Optional, default value is [0, 0].
            Kinematic centre of the rotation in the x-y plane. Units of pixels. Used if the kinematic and
            morphological centres are not the same.
        :param restFreq: 
            (float) Optional, default value =  230.542e9 (12CO(2-1)).
            Rest frequency of spectral line of choice (in Hz). Only matters if you are outputting a FITS file.                 
        ;param radial_motion_func:
            (callable) Optional, default is to not use. 
            If a method of kinms.radial_motion is supplied then will include the effect of radial (non-circular) motions using
            that formalism. Current options include pure radial flows, along with lopsided and bisymmetric (bar-type) flows.
        :param returnClouds: 
            (bool) Optional, default value is False.
            If set True then KinMS returns the created 'inclouds' and 'vlos_clouds' in addition to the cube.
        ;param toplot:
            (bool) Optional, default value is False.
            Makes a basic plot of your model to screen   
        :param vSys: 
            (float) Optional, default value is zero.
            Systemic velocity (km/s).                 
        ;param bunit:
            (string) Optional, default is Jy/beam.
            Unit for the output fits file        
        :param seed: 
            (array or list of float or int) Optional, default value is [100, 101, 102, 103].
            List of length 4 containing the seeds for random number generation.
        :param ra: 
            (float) Optional, default value is None.
            RA to use in the header of the output cube (in degrees).
        :param dec: 
            (float) Optional, default value is None.
            Dec to use in the header of the output cube (in degrees).                 
        :param fileName: 
            (str) Optional, default value is ''.
            If you wish to save the resulting model to a fits file, set this variable. The output filename will
            be 'filename'_simcube.fits                             
        :return: 
            ~~the cube~~
        """
                 
        self.inClouds = np.array(inClouds)
        self.vLOS_clouds = np.array(vLOS_clouds) 
        self.massDist = np.array(massDist)
        self.intFlux = intFlux or 0
        self.phaseCent = np.array(phaseCent) 
        self.vOffset = vOffset or 0
        self.vPhaseCent = np.array(vPhaseCent) 
        self.returnClouds = returnClouds
        self.radial_motion_func=radial_motion_func
        self.bunit=bunit
        self.ra = ra 
        self.dec = dec
        self.vSys = vSys    
        self.restFreq = restFreq or  230.542e9
        self.fileName = fileName
        self.x_pos = None
        self.y_pos = None
        self.z_pos = None
        self.r_flat=None
        
        if self.inClouds.size != 0:
            self.inClouds_given = True
            self.nSamps = self.inClouds.shape[0]
        else:
            self.inClouds_given = False
            
        try:
            if len(inc) > -1:
                self.inc = np.array(inc)
        except:
            self.inc = np.array([inc])
            

        try:
            if len(vPosAng) > -1:
                self.vPosAng = np.array(vPosAng) 
        except:
            self.vPosAng = np.array([vPosAng])
            

        try:
            if len(posAng) > -1:
                self.posAng = np.array(posAng) 
        except:
            self.posAng = np.array([posAng])

        try:
            if len(gasSigma) > -1:
                self.gasSigma = np.array(gasSigma)
        except:
            self.gasSigma = np.array([gasSigma])

        try:
            if len(diskThick) > -1:
                self.diskThick = np.array(diskThick)
        except:
            self.diskThick = np.array([diskThick])

        try:
            if len(sbProf) > -1:
                self.sbProf = np.array(sbProf)
        except:
            self.sbProf = np.array([sbProf])         

        try:
            if len(sbRad) > -1:
                self.sbRad = np.array(sbRad)
        except:
            self.sbRad = np.array([sbRad])

        try:
            if len(velRad) > -1:
                self.velRad = np.array(velRad)
        except:
            self.velRad = np.array([velRad])

        try:
            if len(velProf) > -1:
                self.velProf = np.array(velProf)
        except:
            self.velProf = np.array([velProf])


        if np.any(flux_clouds) != None:
            try:
                if len(flux_clouds) > -1:
                    self.flux_clouds = np.array(flux_clouds)
            except:
                self.flux_clouds = np.array([flux_clouds])
        else:
            self.flux_clouds = None
            
        if self.verbose:
            self.print_variables()
            
                     



        cent = [(self.x_size / 2) + (self.phaseCent[0] / self.cellSize), (self.y_size / 2) + (self.phaseCent[1] / self.cellSize),
                (self.v_size / 2) + (self.vOffset / self.dv)]
        
        self.vPhaseCent = self.vPhaseCent / [self.cellSize, self.cellSize]


        # If cloudlets not previously specified, generate them
        if len(self.inClouds) < 1:
            self.generate_cloudlets()
            

        
        self.set_cloud_positions()
        

        
        
        x2, y2, z2, los_vel = self.set_cloud_velocities()

        
        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#       
        #~~~   POPULATE THE CUBE AND FIND NON-ZERO ELEMENTS   ~~~#~~~~~~~~~~~~#
        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#
        
        
        # Find the clouds inside the cube
        clouds2do, subs = self.find_clouds_in_cube(los_vel, cent, x2, y2)



        # Add fluxes to the clouds
        cube = self.add_fluxes(clouds2do, subs)
        
        

        
        # Convolve with the beam point spread function to obtain a dirty cube
        if not self.cleanOut:

            if not self.huge_beam:  # For very large beams convolve_fft is faster
                    
                for i in range(cube.shape[2]):
                    if np.sum(cube[:, :, i]) > 0:
                        cube[:, :, i] = convolve(cube[:, :, i], self.psf) 

             
            else:
                    
                for i in range(cube.shape[2]):
                    if np.sum(cube[:, :, i]) > 0:
                        cube[:, :, i] = convolve_fft(cube[:, :, i], self.psf)  

        # Convolve with the line spread function (LSF) with fast fft if specified. 
        if self.lsf_fwhm != None:
            
            # convolve lsf with cube in the spectral direction
            for i in range(cube.shape[0]):
                for j in range(cube.shape[1]):
                    if np.sum(cube[i, j, :]) > 0:
                        cube[i, j, :] = convolve(cube[i, j, :], self.lsf)

                            
        # Normalise the cube by known integrated flux

        self.normalise_cube(cube, self.psf)

        

        # If appropriate, generate the FITS file header and save to disc.
        if self.fileName:
            self.save_fits(cube, cent)
        
        # Plot the results if so desired
        if toplot:
            if len(self.posAng)>1:
                posAng_plotting = float(np.median(self.posAng))
                if self.verbose == True:
                    print('_' * 37 + '\n\n *** WARNING! posAng warp detected: Using the average posAng for plotting the pvd, calculated as: %.2f' \
                          % posAng_plotting, 'degrees *** \n\n' + '_' * 37)
            else:
                posAng_plotting = float(self.posAng)
                      
            KinMS_plotter(cube, self.xs, self.ys, self.vs, self.cellSize, self.dv, self.beamSize,
                          posang = posAng_plotting,**kwargs).makeplots()
                          
                          
        
        # Output the final cube
        if self.returnClouds:
            retClouds = np.empty((self.nSamps, 3))
            retClouds[:, 0] = x2 * self.cellSize
            retClouds[:, 1] = y2 * self.cellSize
            retClouds[:, 2] = z2 * self.cellSize

            if self.verbose:
                print('_' * 37 + '\n\n *** Cube successfully created ***')

            return cube, retClouds, los_vel

        else:
            if self.verbose:
                print('_' * 37 + '\n\n *** Cube successfully created ***')

            return cube
    
    #=========================================================================#
    #/////////////////////////////////////////////////////////////////////////#
    #=========================================================================#
    
#=============================================================================#
#/// END OF CLASS ////////////////////////////////////////////////////////////#
#=============================================================================#

#=============================================================================#
#/// END OF SCRIPT ///////////////////////////////////////////////////////////#
#=============================================================================#

                                     