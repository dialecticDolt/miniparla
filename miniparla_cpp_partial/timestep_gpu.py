import cupy as cp
import numpy as np
import numba
from numba import cuda

import math
import time

from miniparla import Parla
from miniparla.barriers import TaskSpace
from miniparla.spawn import spawn

from sleep.core import bsleep, sleep_with_gil

import argparse

def to_numba(cp_stream):
    '''
    Notes:
        1. The lifetime of the returned Numba stream should be as long as the CuPy one,
           which handles the deallocation of the underlying CUDA stream.
        2. The returned Numba stream is assumed to live in the same CUDA context as the
           CuPy one.
        3. The implementation here closely follows that of cuda.stream() in Numba.
    '''
    from ctypes import c_void_p
    import weakref

    # get the pointer to actual CUDA stream
    raw_str = cp_stream.ptr

    # gather necessary ingredients
    ctx = cuda.devices.get_context()
    handle = c_void_p(raw_str)
    finalizer = None  # let CuPy handle its lifetime, not Numba

    # create a Numba stream
    nb_stream = cuda.cudadrv.driver.Stream(weakref.proxy(ctx), handle, finalizer)

    return nb_stream

@cuda.jit
def increment(array, counter):
    x, y = cuda.grid(2)
    for c in range(counter):
        if x < array.shape[0] and y < array.shape[1]:
            array[x, y] += 1.0

def increment_wrapper(array, counter, stream):

    threadsperblock  = (16, 16)
    blocks_x = math.ceil(array.shape[0] / threadsperblock[0])
    blocks_y = math.ceil(array.shape[1] / threadsperblock[1])
    blocks = (blocks_x, blocks_y)

    nb_stream = to_numba(stream)

    increment[blocks, threadsperblock, nb_stream](array, counter)

def main(N, d, steps, NUM_WORKERS, gpu_array, sync_flag, vcu_flag, dep_flag, verbose):

    @spawn(placement=cpu, vcus=0)
    async def main_task():

        T = TaskSpace("Outer")
        a = 1

        start_t = time.perf_counter()
        for t in range(steps):

            for ng in range(NUM_WORKERS):
                loc = gpu(ng)
                if dep_flag or (t == 0):
                    deps = []
                else:
                    deps = [T[1, t-1, ng]]

                if vcu_flag:
                    vcus = 1
                else:
                    vcus = 0

                @spawn(T[1, t, ng], dependencies=deps, placement=loc, vcus=vcus)
                def task():

                    if verbose:
                        print("Task", [1, t, ng], " started.", flush=True)
                        inner_start_t = time.perf_counter()
                        stream = cp.cuda.get_current_stream()

                    cuda.select_device(ng)

                    #A = gpu_array[ng].T @ gpu_array[ng]

                    #gpu_array[ng] = cp.random.rand(N, d)
                    increment_wrapper(gpu_array[ng], 1000, stream)
                    #A = cp.random.rand(N, d)
                    #A = np.random.rand(N, d)

                    if verbose:
                        stream.synchronize()
                        inner_end_t = time.perf_counter()
                        inner_elapsed = inner_end_t - inner_start_t
                        print("Task", [1, t, ng], "Finished. I took ", inner_elapsed, flush=True)
                        #print("I am task", [1, t, ng], ". I took ", inner_elapsed, ". on device", A.device, flush=True)

            if sync_flag:
                await T

        if not sync_flag:
            await T
        end_t = time.perf_counter()

        elapsed = end_t - start_t
        print("Elapsed: ", elapsed, flush=True)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--steps', type=int, default=1)
    parser.add_argument('-d', type=int, default=7)
    parser.add_argument('-n', type=int, default=2**23)
    parser.add_argument('--isync', type=int, default=0)
    parser.add_argument('--vcus', type=int, default=0)
    parser.add_argument('--deps', type=int, default=0)
    parser.add_argument('--verbose', type=int, default=0)
    args = parser.parse_args()



    NUM_WORKERS = args.workers
    STEPS = args.steps
    N = args.n
    d = args.d
    isync = args.isync

    gpu_array = []
    for ng in range(NUM_WORKERS):
       with cp.cuda.Device(ng) as device:
            #cp.cuda.set_allocator(cp.cuda.MemoryAsyncPool().malloc)
            gpu_array.append(cp.zeros([N, d]))
            stream = cp.cuda.get_current_stream()
            increment_wrapper(gpu_array[ng], 1, stream)

            device.synchronize()

    with Parla():
        main(N, d, STEPS, NUM_WORKERS, gpu_array, isync, args.vcus, args.deps, args.verbose)
