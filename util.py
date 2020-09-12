import os
import itertools

def vs_arch_to_android(vs_arch):
    all_arch = {}
    all_arch['ARM'] = 'armeabi-v7a'
    all_arch['ARM64'] = 'arm64-v8a'
    all_arch['x86'] = 'x86'
    all_arch['x64'] = 'x86_64'
    return all_arch[vs_arch]

def vs_target_to_clang(vs_target):
    if vs_target == 'StaticLibrary':
        tt = 'STATIC'
    elif vs_target == 'DynamicLibrary':
        tt = 'SHARED'
    else:
        assert False, "Did not target:{}".format(vs_target)
    return tt

def make_arch_group(release, arch):
    return list(itertools.product(release, arch))
