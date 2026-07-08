#ifdef MATLAB_MEX_FILE
#include <mex.h>
#else /*MATLAB_MEX_FILE*/
// If you don't have mex on your machine, these will give similar types to test compilation
#include <stdint.h>
typedef uint64_t mxUint64;
typedef double mxDouble;
#endif /*MATLAB_MEX_FILE*/

typedef struct {
    mxUint64 *macrotimes;
    mxDouble *weights;
    mxUint64 number_of_photons;
} channel;

/**
 * @brief Calculate correlation for one block
 *
 * @details
 * Iterates over pairs of photons with macrotimes within a certain range of each other (time delay)
 * Important: result is not normalized based on bin size!
 *
 * @param[in] channel_1 First channel
 * @param[in] channel_2 Second channel
 * @param[in] number_per_block Size of \p correlation array, gives the number of distinct time delays in a block
 * @param[in] minimal_offset minimal offset between first and second photon macrotime
 * @param[out] correlation Array to place the calculated correlations into
 */
void correlate_block(const channel *channel_1, const channel *channel_2,
                     mxUint64 number_per_block, mxUint64 minimal_offset,
                     mxDouble *correlation) {

    // the starting photon in second array,
    // any points to the left would never contribute
    mxUint64 photon_2_min_index = 0;

    for (mxUint64 photon_1 = 0; photon_1 < channel_1->number_of_photons;
         photon_1++) {
        // Calculates minimal and maximal time
        // for photons in second array

        mxUint64 lower_limit = minimal_offset + channel_1->macrotimes[photon_1];
        mxUint64 upper_limit = lower_limit + number_per_block;

        for (mxUint64 photon_2 = photon_2_min_index;
             photon_2 < channel_2->number_of_photons; photon_2++) {
            if (channel_2->macrotimes[photon_2] >= upper_limit) {
                break; // passed the limit of the block
            }
            if (channel_2->macrotimes[photon_2] >= lower_limit) {
                // Calculates time between two photons
                mxUint64 index = channel_2->macrotimes[photon_2] - lower_limit;
                // Add to correlation at the appropriate timelag
                correlation[index] +=
                    channel_1->weights[photon_1] * channel_2->weights[photon_2];
            } else {
                // Increases starting photon in second array,
                // to save time
                photon_2_min_index++;
            }
        }
    }
}

/**
 * @brief Bins the neighboring values of an array by addition.
 *
 * @details
 * The neighbors are binned by checking if they are equal under the `// 2`
 * operation (e.g. 4,5 -> 2,2 which are equal). When two indices are equal in
 * the \p index_array , the sum of the values in \p value_array is placed in the
 * right neighbor and the left neighbor is set to zero. Both arrays are edited
 * in place.
 *
 * @param[in,out] index_array Array of indices to check for neighbors to be
 * binned
 * @param[in,out] value_array Values that will be add together at the
 * corresponding index
 * @param[in] size Size of array
 */
void bin_neighbors(mxUint64 *index_array, mxDouble *value_array, mxUint64 size) {
    for (mxUint64 i = 0; i < size; i++) {
        index_array[i] /= 2;
        // normalization could be performed here, but is done in correlation instead
        // value_array[i] /= sqrt(2.0);
    }
    for (mxUint64 i = 1; i < size; i++) {
        if (index_array[i] == index_array[i - 1]) {
            value_array[i] += value_array[i - 1];
            value_array[i - 1] = 0;
        }
    }
}

/**
 * @brief Moves all non-zero values to the start of the array, keeping their
 * order.
 *
 * @param[in,out] index_array Represents indices of the respective values in \p
 * value_array
 * @param[in,out] value_array Values which will be pruned if zero
 * @param[in] size Size of the \p index_array and \p value_array
 * @return mxUint64 Index up to which non-zero values are placed
 *                  (effective new size, any indices above this value should not
 * be used).
 */
mxUint64 prune_zeros(mxUint64 *index_array, mxDouble *value_array, mxUint64 size) {
    mxUint64 last_nonzero_index = 0;
    for (mxUint64 i = 0; i < size; i++) {
        if (value_array[i] == 0) {
            continue; // skip zero values
        }
        value_array[last_nonzero_index] = value_array[i];
        index_array[last_nonzero_index] = index_array[i];
        last_nonzero_index++;
    }
    return last_nonzero_index;
}

/**
 * @brief Computes cross-correlation between two photon bins
 *
 * @details
 * Computes the array of cross-correlations between two channels of photons.
 * The index of the array gives the time delay of a correlation according to a
 * linear scale with exponentially increasing gaps. These are given in blocks
 * (example with block_size = 10):
 * zero-delay:                   0,
 * block 0:    1,  2,  3,  ..., 10,
 * block 1:    11, 12, 13, ..., 20,
 * block 2:    22, 24, 26, ..., 40,
 * block 3:    44, 48, 52, ..., 80,
 * ...
 *
 * Starting from block 2, the values are binned together by summation of their weights.
 * This means the computed correlation is now (example for block 2, which has gaps of size 2):
 * (w(i) + w(i+1)) * (w(i+d) + w(i+1+d))
 *  = [w(i+1) * w(i+d)] + [w(i) * w(i + d) + w(i+1) * w(i+1+d)] + [w(i) * w(i+1+d)]
 * Where d is the time delay (corresponding to some index in the correlation array),
 * and i is the index being summed over.
 * The expanded terms are organized by the effective time delays:
 * [1 term of d - 1] + [2 terms of d] + [1 term of d + 1]
 * Therefore the binning is centered around the term of time delay [d].
 * Note that this requires normalizing by dividing by 2
 * (because the of the 2 terms for time delay [d]).
 *
 * The sum becomes more extensive as you move down the blocks with larger gaps.
 *
 * The algorithm is equivalent to the following idea:
 * First compute the entire correlation array (for all time delays, with no binning).
 * Then apply a moving average over the different blocks of this array:
 * For the first 2 blocks (e.g. first 20 elements): no averaging needed
 * For the 3rd block:
 *          Use averaging window [1, 2, 1] with a step size of 2, and apply normalization of 2.
 * For the 4th block:
 *          Use averaging window [1, 2, 3, 4, 3, 2, 1] with a step size of 4, and apply normalization of 4.
 * ...
 *
 * @param[in] macrotimes_1 the macrotimes of the first channel
 * @param[in] macrotimes_2 the macrotimes of the second channel
 * @param[in] weights_1 photon weights of the first channel
 * @param[in] weights_2 photon weights of the second channel
 * @param[in] block_size number of evenly spaced elements per block
 * @param[in] number_of_blocks number of blocks (different blocks may have
 * different spacings)
 * @param[in] number_of_photons_1 total number of photons in first channel
 * @param[in] number_of_photons_2 total number of photons in second channel
 * @param[out] correlation the computed cross-correlation array
 */
void fast_MT(mxUint64 *macrotimes_1, mxUint64 *macrotimes_2, mxDouble *weights_1,
             mxDouble *weights_2, mxUint64 block_size, mxUint64 number_of_blocks,
             mxUint64 number_of_photons_1, mxUint64 number_of_photons_2,
             mxDouble *correlation) {
    if (number_of_blocks == 0) {
        return; // nothing to do
    }

    channel channel_1 = {macrotimes_1, weights_1, number_of_photons_1};
    channel channel_2 = {macrotimes_2, weights_2, number_of_photons_2};

    // jump across blocks of size block_size
    mxDouble *block = correlation;

    // first correlation is normal and gives the zero-delay correlation and block 0,
    // it calculates correlation distance from 0 (inclusive) up to block_size + 1 (exclusive)
    correlate_block(&channel_1, &channel_2, block_size + 1, 0, block);

    // jump by one due to zero-delay offset
    block += 1;

    // next correlations will use logscale binning

    // used to normalize correlation based on bin size
    mxUint64 binning_factor = 1;

    for (mxUint64 block_number = 1; block_number < number_of_blocks;
         block_number++) {
        block += block_size;

        correlate_block(&channel_1, &channel_2, block_size, block_size + 1, block);
        // apply normalization to account for binning
        for (mxUint64 i = 0; i < block_size; i++) {
            block[i] /= binning_factor;
        }

        // Bin neighboring photons together
        binning_factor *= 2;

        // Determines how many neighbors are binned together
        // never called    (1) -> no binning
        // called once     (2) -> pairs are binned into one
        // called twice    (4) -> pairs of pairs are binned into one
        // ...
        // called n times (2^n)
        bin_neighbors(channel_1.macrotimes, channel_1.weights,
                      channel_1.number_of_photons);
        bin_neighbors(channel_2.macrotimes, channel_2.weights,
                      channel_2.number_of_photons);

        // performance optimization: prune the zero values produced above,
        // since they will not change the value of the correlation

        // filter zeros and change number_of_photons
        // to only include non-zero values
        channel_1.number_of_photons = prune_zeros(
            channel_1.macrotimes, channel_1.weights, channel_1.number_of_photons);
        channel_2.number_of_photons = prune_zeros(
            channel_2.macrotimes, channel_2.weights, channel_2.number_of_photons);
    }
}

#ifdef MATLAB_MEX_FILE

// helper functions to get data
mxDouble *getDoubles(const mxArray *array_ptr) {
    if (!mxIsDouble(array_ptr)) {
        mexErrMsgIdAndTxt("PAM:Do_CCF:getDoubles:incorrectType",
                          "Expected type: Double, Received: classID %d",
                          mxGetClassID(array_ptr));
    }
#if MX_HAS_INTERLEAVED_COMPLEX
    return mxGetDoubles(array_ptr);
#else
    return (mxDouble *)mxGetPr(array_ptr);
#endif
}

mxUint64 *getUint64s(const mxArray *array_ptr) {
    if (!mxIsUint64(array_ptr)) {
        mexErrMsgIdAndTxt("PAM:Do_CCF:getUint64s:incorrectType",
                          "Expected type: Uint64, Received: classID %d",
                          mxGetClassID(array_ptr));
    }
#if MX_HAS_INTERLEAVED_COMPLEX
    return mxGetUint64s(array_ptr);
#else
    return (mxUint64 *)mxGetPr(array_ptr);
#endif
}

///////////////////////////////////////////////////////////////////////////
// This function is called from matlab  ///////////////////////////////////
///////////////////////////////////////////////////////////////////////////
// nlhs is the number of output parameter
// *plhs is an array of pointers to the output parameters
// nrhs is the number of input parameters
// *prhs is an array of pointers to the input parameters
void mexFunction(int nlhs, mxArray *plhs[], int nrhs, const mxArray *prhs[]) {
    if (nrhs != 8) {
        mexErrMsgIdAndTxt("PAM:Do_CCF:invalidNumInputs",
                          "Do_CCF requires exactly 8 arguments.");
    }
    // Duplicate data that should not be edited.
    // No need to call mxFree, matlab will do this automatically.
    mxArray *mt1_arr = mxDuplicateArray(prhs[0]);
    mxArray *mt2_arr = mxDuplicateArray(prhs[1]);
    mxArray *w1_arr = mxDuplicateArray(prhs[2]);
    mxArray *w2_arr = mxDuplicateArray(prhs[3]);
    // Assigns input pointers to initialized pointers
    mxUint64 *mt1 = getUint64s(mt1_arr);
    mxUint64 *mt2 = getUint64s(mt2_arr);
    mxDouble *w1 = getDoubles(w1_arr);
    mxDouble *w2 = getDoubles(w2_arr);

    // mxUint64 nc = mxGetScalar(prhs[4]);
    // mxUint64 nb = mxGetScalar(prhs[5]);
    // mxUint64 np1 = mxGetScalar(prhs[6]);
    // mxUint64 np2 = mxGetScalar(prhs[7]);
    mxUint64 nc = getUint64s(prhs[4])[0];
    mxUint64 nb = getUint64s(prhs[5])[0];
    mxUint64 np1 = getUint64s(prhs[6])[0];
    mxUint64 np2 = getUint64s(prhs[7])[0];

    // Initializes output matrix and assigns pointer to it
    plhs[0] = mxCreateDoubleMatrix(1, 1 + nb * nc, mxREAL);
    mxDouble *corrl = getDoubles(plhs[0]);

    // Calls function to do the actual work
    fast_MT(mt1, mt2, w1, w2, nc, nb, np1, np2, corrl);
};

#endif /*MATLAB_MEX_FILE*/
