// Minimal stand-in for MATLAB's MEX API, just enough to run PAM's kernels natively.
#pragma once
#include <cstdlib>
#include <cstdio>
#include <cstdint>
#include <cstddef>
typedef size_t mwSize;
enum mxClassID { mxDOUBLE_CLASS, mxUINT16_CLASS, mxUINT8_CLASS, mxUINT64_CLASS };
enum mxComplexity { mxREAL };
struct mxArray { void *data; int64_t n; };
inline double mxGetScalar(const mxArray *a) { return ((double *)a->data)[0]; }
inline double *mxGetPr(const mxArray *a) { return (double *)a->data; }
inline void *mxCalloc(size_t n, size_t s) { return calloc(n, s); }
inline mxArray *mxCreateNumericArray(int, const mwSize *dims, mxClassID, mxComplexity) {
    mxArray *a = new mxArray; a->data = nullptr; a->n = (int64_t)(dims[0] * dims[1]); return a; }
inline void mxSetData(mxArray *a, void *d) { a->data = d; }
inline void mexErrMsgIdAndTxt(const char *, const char *msg, ...) { fprintf(stderr, "%s\n", msg); abort(); }
