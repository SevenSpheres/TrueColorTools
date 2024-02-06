""" File containing constant and functions required in various places, but without dependencies """

import numpy as np
from typing import Sequence
import src.strings as tr


# TCT was written in an effort to work not only with the optical range, but with any, depending on the data.
# But too long and heterogeneous FITS files demanded to set the upper limit of the range to mid-wavelength infrared (3 μm).
nm_red_limit = 3000 # nm
# Actually, dtype=uint16 is used to store wavelength. It's possible to set the limit to 65535 nm with no compression,
# and to 327 675 nm with 5 nm compression.

# For the sake of simplifying work with the spectrum, its discretization step in only 5 nm.
resolution = 5 # nm

# To calculate color, it is necessary to achieve a definition of the spectrum in the visible range.
# Boundaries have been defined based on the CMF (color matching functions) used, but can be any.
visible_range = np.arange(390, 780, 5) # nm

# Constants needed for down scaling spectra and images
# TODO: down scale spectra properly
fwhm_factor = np.sqrt(8*np.log(2))
hanning_factor = 1129/977


# Math operations

def get_resolution(array: Sequence):
    return np.mean(np.diff(array)) * hanning_factor

def gaussian_width(current_resolution, target_resolution):
    return ((target_resolution**2 - current_resolution**2)**0.5 / current_resolution / fwhm_factor)

def grid(start: int|float, end: int|float, res: int):
    """ Returns uniform grid points for the non-integer range that are divisible by the selected step """
    if (shift := start % res) != 0:
        start += res - shift
    if end % res == 0:
        end += 1 # to include the last point
    return np.arange(start, end, res, dtype='uint16')

def is_smooth(array: Sequence|np.ndarray):
    """ Boolean function, checks the second derivative for sign reversal, a simple criterion for smoothness """
    diff2 = np.diff(np.diff(array, axis=0), axis=0)
    return np.all(diff2 <= 0) | np.all(diff2 >= 0)

def integrate(array: Sequence|np.ndarray, step: int|float):
    """ Riemann sum with midpoint rule for integrating both spectra and spectral cubes """
    return step * 0.5 * np.sum(array[:-1] + array[1:])

def averaging(x0: Sequence, y0: np.ndarray, x1: Sequence, step: int|float):
    """ Returns spectrum brightness values with decreased resolution """
    semistep = step * 0.5
    y1 = [np.mean(y0[np.where(x0 < x1[0]+semistep)])]
    for x in x1[1:-1]:
        flag = np.where((x-semistep < x0) & (x0 < x+semistep))
        if flag[0].size == 0: # the spectrum is no longer dense enough to be averaged down to 5 nm
            y = y1[-1] # lengthening the last recorded brightness is the simplest solution
        else:
            y = np.mean(y0[flag]) # average the brightness around X points
        y1.append(y)
    y1.append(np.mean(y0[np.where(x0 > x1[-1]-semistep)]))
    return np.array(y1)

def custom_interp(xy0: np.ndarray, k=16):
    """
    Returns curve values with twice the resolution. Can be used in a loop.
    Optimal in terms of speed to quality ratio: around 2 times faster than splines in scipy.

    Args:
    - `xy0` (np.ndarray): values to be interpolated in shape (2, N)
    - `k` (int): lower -> more chaotic, higher -> more linear, best results around 10-20
    """
    xy1 = np.empty((2, xy0.shape[1]*2-1), dtype=xy0.dtype)
    xy1[:,0::2] = xy0
    xy1[:,1::2] = (xy0[:,:-1] + xy0[:,1:]) * 0.5
    delta_left = np.append(0., xy0[1,1:-1] - xy0[1,:-2])
    delta_right = np.append(xy0[1,2:] - xy0[1,1:-1], 0.)
    xy1[1,1::2] += (delta_left - delta_right) / k
    return xy1

def interpolating(x0: Sequence, y0: np.ndarray, x1: Sequence, step: int|float) -> np.ndarray:
    """
    Returns interpolated brightness values on uniform grid.
    Combination of custom_interp (which returns an uneven mesh) and linear interpolation after it.
    The chaotic-linearity parameter increases with each iteration to reduce the disadvantages of custom_interp.
    """
    xy0 = np.array([x0, y0])
    for i in range(int(np.log2(np.diff(x0).max() / step))):
        xy0 = custom_interp(xy0, k=11+i)
    return np.interp(x1, xy0[0], xy0[1])

def scope2cube(scope: Sequence, shape: tuple[int, int]):
    """ Gets ta 1D array and expands its dimensions to a 3D array based on the 2D slice shape """
    return np.repeat(np.repeat(np.expand_dims(scope, axis=(1, 2)), shape[0], axis=1), shape[1], axis=2)

def custom_extrap(grid: Sequence, derivative: float|np.ndarray, corner_x: int|float, corner_y: float|np.ndarray) -> np.ndarray:
    """
    Returns an intuitive continuation of the function on the grid using information about the last point.
    Extrapolation bases on function f(x) = exp( (1-x²)/2 ): f' has extrema of ±1 in (-1, 1) and (1, 1).
    Therefore, it scales to complement the spectrum more easily than similar functions.
    """
    if np.all(derivative) == 0: # extrapolation by constant
        return np.repeat(np.expand_dims(corner_y, axis=0), grid.size, axis=0)
    else:
        if corner_y.ndim == 2: # spectral cube processing
            grid = scope2cube(grid, corner_y.shape)
        sign = np.sign(derivative)
        return np.exp((1 - (np.abs(derivative) * (grid - corner_x) / corner_y - sign)**2) / 2) * corner_y

weights_center_of_mass = 1 - 1 / np.sqrt(2)

def extrapolating(x: np.ndarray, y: np.ndarray, scope: np.ndarray, step: int|float, avg_steps=20):
    """
    Defines a curve or a cube with an intuitive continuation on the scope, if needed.
    `avg_steps` is a number of corner curve points to be averaged if the curve is not smooth.
    Averaging weights on this range grow linearly closer to the edge (from 0 to 1).
    """
    if len(x) == 1: # filling with equal-energy spectrum
        x = np.arange(min(scope[0], x[0]), max(scope[-1], x[0])+1, step, dtype='uint16')
        y = np.repeat(np.expand_dims(y[0], axis=0), x.size, axis=0)
    else:
        # Extrapolation to blue
        if x[0] > scope[0]:
            x1 = np.arange(scope[0], x[0], step)
            y_scope = y[:avg_steps]
            if is_smooth(y_scope):
                diff = y[1]-y[0]
                corner_y = y[0]
            else:
                avg_weights = np.abs(np.arange(-avg_steps, 0)[avg_steps-y_scope.shape[0]:]) # weights could be more complicated, but there is no need
                if y.ndim == 3: # spectral cube processing
                    avg_weights = scope2cube(avg_weights, y.shape[1:3])
                diff = np.average(np.diff(y_scope, axis=0), weights=avg_weights[:-1], axis=0)
                corner_y = np.average(y_scope, weights=avg_weights, axis=0) - diff * avg_steps * weights_center_of_mass
            y1 = custom_extrap(x1, diff/step, x[0], corner_y)
            x = np.append(x1, x)
            y = np.append(y1, y, axis=0)
        # Extrapolation to red
        if x[-1] < scope[-1]:
            x1 = np.arange(x[-1], scope[-1], step) + step
            y_scope = y[-avg_steps:]
            if is_smooth(y_scope):
                diff = y[-1]-y[-2]
                corner_y = y[-1]
            else:
                avg_weights = np.arange(avg_steps)[:y_scope.shape[0]] + 1
                if y.ndim == 3: # spectral cube processing
                    avg_weights = scope2cube(avg_weights, y.shape[1:3])
                diff = np.average(np.diff(y_scope, axis=0), weights=avg_weights[1:], axis=0)
                corner_y = np.average(y_scope, weights=avg_weights, axis=0) + diff * avg_steps * weights_center_of_mass
            y1 = custom_extrap(x1, diff/step, x[-1], corner_y)
            x = np.append(x, x1)
            y = np.append(y, y1, axis=0)
    return x, y


# Front-end

def obj_dict(database: dict, tag: str, lang: str):
    """ Maps front-end spectrum names allowed by the tag to names in the database """
    names = {}
    for raw_name, obj_data in database.items():
        if tag == '_all_':
            flag = True
        else:
            try:
                flag = tag in obj_data['tags']
            except KeyError:
                flag = False
        if flag:
            if '|' in raw_name:
                new_name, source = raw_name.split('|', 1)
            else:
                new_name, source = raw_name, ''
            if lang != 'en': # parsing and translating
                index = ''
                if new_name[0] == '(': # minor body index or stellar spectral type parsing
                    parts = new_name.split(')', 1)
                    index = parts[0] + ') '
                    new_name = parts[1].strip()
                elif '/' in new_name: # comet name parsing
                    parts = new_name.split('/', 1)
                    index = parts[0] + '/'
                    new_name = parts[1].strip()
                note = ''
                if ':' in new_name:
                    parts = new_name.split(':', 1)
                    note = parts[1].strip()
                    new_name = parts[0].strip()
                    note = ': ' + translate(note, tr.notes, lang)
                new_name = index + translate(new_name, tr.names, lang) + note
            new_name = new_name if source == '' else f'{new_name} [{source}]'
            names |= {new_name: raw_name}
    return names

def translate(target: str, translations: dict, lang: str):
    """ Searches part of the target string to be translated and replaces it with translation """
    for original, translation in translations.items():
        if target.startswith(original) or original in target.split():
            target = target.replace(original, translation[lang])
            break
    return target

def tag_list(database: dict):
    """ Generates a list of tags found in the spectra database """
    tag_set = set(['_all_'])
    for obj_data in database.values():
        if 'tags' in obj_data:
            tag_set.update(obj_data['tags'])
    return sorted(tag_set)

def notes_list(names: Sequence):
    """ Generates a list of notes found in the spectra database """
    notes = []
    for name in names:
        if ':' in name:
            if '[' in name:
                name = name.split('[', -1)[0]
            note = name.split(':')[1].strip()
            if note not in notes:
                notes.append(note)
    return notes

def export_colors(rgb: tuple):
    """ Generates formatted string of colors """
    lst = []
    mx = 0
    for i in rgb:
        lst.append(str(i))
        l = len(lst[-1])
        if l > mx:
            mx = l
    w = 8 if mx < 8 else mx+1
    return ''.join([i.ljust(w) for i in lst])

def get_flag_index(flags: tuple):
    """ Returns index of active radio button """
    for index, flag in enumerate(flags):
        if flag:
            return index