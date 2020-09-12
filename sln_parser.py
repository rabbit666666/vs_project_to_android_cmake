import util
import os
import codecs
import cmake_converter.visual_studio.context as vs_context
import cmake_converter.visual_studio.solution as vs_solution
import cmake_converter.visual_studio.vcxproj.parser as vcxproj

class SlnParser:
    def __init__(self, file):
        self._project = {}
        self._file = file
        self._proj_name = os.path.splitext(os.path.split(self._file)[1])[0]
        self._vs_ctx = vs_context.VSContext()
        self._vs_ctx.is_android = True
        self._sln_parser = vs_solution.VSSolutionConverter()
        self._sln_dir = os.path.dirname(file)
        self._cmake_file = os.path.join(self._sln_dir, 'CMakeLists.txt')

    def parse(self):
        with codecs.open(self._file, 'r', encoding='utf8') as fd:
            content = fd.read()
        proj_lst = self._sln_parser.parse_solution(self._vs_ctx, content)
        for (k, v) in proj_lst['sln_projects_data'].items():
            name = v['name']
            vc_proj_path = os.path.normpath(os.path.join(self._sln_dir, v['path']))
            deps = v.get('sln_deps') and v['sln_deps'] or []
            self._project[name] = {
                'name': name,
                'path': vc_proj_path,
                'deps': deps,
            }
        print(self._project)
        return self._project

    def get_project_sequence(self):
        seq = []
        for (name, info) in self._project.items():
            for other in info['deps']:
                if other not in seq:
                    seq.append(name)
            if name not in seq:
                seq.append(name)
        return seq

    def gen_cmake(self):
        sorted_proj = self.get_project_sequence()
        code = ['cmake_minimum_required(VERSION 3.6.0)']
        code.append('project({})'.format(self._proj_name))
        for proj in sorted_proj:
            proj_path = self._project[proj]['path']
            proj_path = os.path.relpath(proj_path, self._sln_dir).replace('\\', '/')
            proj_dir = os.path.dirname(proj_path)
            code.append('add_subdirectory({})'.format(proj_dir))
        code = '\n'.join(code)
        with open(self._cmake_file, 'w') as fd:
            fd.write(code)

class VcProjectParser:
    def __init__(self, proj_desc):
        self._project = {}
        self._proj_desc = proj_desc
        self._vc_ctx = vs_context.VSContext()
        self._vc_ctx.is_android = True
        self._vc_ctx.init_context_for_vcxproj()
        self._vcproj_parser = vcxproj.VCXParser()
        self._support_arch = util.make_arch_group(['Debug'], ['x86', 'x64', 'ARM', 'ARM64'])
        self._vc_ctx.configurations_to_parse = self._support_arch

    def parse(self):
        print(self._proj_desc)
        self._vc_ctx.vcxproj_path = self._proj_desc['path']
        self._vcproj_parser.parse(self._vc_ctx)
        self._proj_name = self._vc_ctx.project_name or self._vc_ctx.root_namespace
        self._proj_files = list(self._vc_ctx.file_contexts.keys())
        self._proj_settings = self._vc_ctx.settings

    def get_includes(self):
        code = ''
        for (dis_type, arch) in self._support_arch:
            inc_dirs = []
            for f in self._proj_settings[(dis_type, arch)]['inc_dirs']:
                dir_name = 'PUBLIC {}'.format(f)
                inc_dirs.append(dir_name)
            inc_dirs = '\n\t'.join(inc_dirs)
            android_arch = util.vs_arch_to_android(arch)
            code = code + '''
if ((${{ANDROID_ABI}} STREQUAL "{android_arch}") AND (${{CMAKE_BUILD_TYPE}} STREQUAL "{dis_type}"))
    include_directories(
        {inc_dirs}
    )
endif()'''.format(inc_dirs=inc_dirs, android_arch=android_arch, dis_type=dis_type)
        return code

    def get_dep_library_path(self):
        code = ''
        for (dis_type, arch) in self._support_arch:
            lib_dirs = ['${CMAKE_LIBRARY_OUTPUT_DIRECTORY}']
            for f in self._proj_settings[(dis_type, arch)]['target_link_dirs']:
                if f.find('$(OutputPath)') != -1:
                    continue
                lib_dirs.append(f)
            lib_dirs = '\n\t'.join(lib_dirs)
            android_arch = util.vs_arch_to_android(arch)
            code = code + '''
if ((${{ANDROID_ABI}} STREQUAL "{android_arch}") AND (${{CMAKE_BUILD_TYPE}} STREQUAL "{dis_type}"))
    link_directories(            
        {lib_dirs}
    )
endif()
'''.format(lib_dirs=lib_dirs, android_arch=android_arch, dis_type=dis_type)
        return code

    def get_target_link_libs(self):
        code = ''
        for (dis_type, arch) in self._support_arch:
            setting = self._proj_settings[(dis_type, arch)]
            libs = setting['add_lib_deps']
            if setting.get('use_of_stl'):
                libs.append(setting['use_of_stl'])
            android_arch = util.vs_arch_to_android(arch)
            code = code + '''
if ((${{ANDROID_ABI}} STREQUAL "{android_arch}") AND (${{CMAKE_BUILD_TYPE}} STREQUAL "{dis_type}"))
    target_link_libraries({proj_name} {libs})
endif()
'''.format(proj_name=self._proj_name, libs=' '.join(libs), android_arch=android_arch, dis_type=dis_type)
        return code

    def get_cl_flags(self):
        code = ''
        for (dis_type, arch) in self._support_arch:
            flag_lst = self._proj_settings[(dis_type, arch)]['cl_flags']
            c_flags = []
            cxx_flags = []
            for flag in flag_lst:
                if flag in ['-std=c++1z']:
                    cxx_flags.append(flag)
                if flag in ['-std=c11']:
                    c_flags.append(flag)
            flag_lst = []
            for macro in self._proj_settings[(dis_type, arch)]['defines']:
                flag_lst.append('-D{}'.format(macro))
            macro_def = ' '.join(flag_lst)
            c_flags = ' '.join(c_flags)
            cxx_flags = ' '.join(cxx_flags)
            android_arch = util.vs_arch_to_android(arch)
            code = code + '''
message(STATUS ">>>>build_type:" ${{CMAKE_BUILD_TYPE}})
if ((${{ANDROID_ABI}} STREQUAL "{android_arch}"))
    if (${{CMAKE_BUILD_TYPE}} STREQUAL "Release")
        set(CMAKE_C_FLAGS "${{CMAKE_C_FLAGS}} -g -O3 {c_flags} {macro_def}")
        set(CMAKE_CXX_FLAGS "${{CMAKE_CXX_FLAGS}} -g -O3 {cxx_flags} {macro_def}")
    else()
        set(CMAKE_C_FLAGS "${{CMAKE_C_FLAGS}} -g -O0 {c_flags} {macro_def}")
        set(CMAKE_CXX_FLAGS "${{CMAKE_CXX_FLAGS}} -g -O0 {cxx_flags} {macro_def}")
    endif()
endif()
'''.format(macro_def=macro_def, android_arch=android_arch, dis_type=dis_type, cxx_flags=cxx_flags, c_flags=c_flags)
        return code

    def gen_cmake(self):
        proj_dir = os.path.dirname(self._vc_ctx.vcxproj_path)
        check_version = 'cmake_minimum_required(VERSION 3.6.0)'
        cl_flags = self.get_cl_flags()                  # compile flags, need arch branch
        output_dir = self.get_output_dir()              # out dir, don't need arch
        include_dir = self.get_includes()               # header include, need arch branch
        lib_include = self.get_dep_library_path()       # lib include, need arch branch
        target_links = self.get_target_link_libs()      # dep libraries, need arch branch
        add_library = self.get_add_library()            # source files, don't need arch
        cmake_txt = '''{check_version}\n
project({proj_name})\n
{output_dir}\n    
{cl_flags}\n
{include_dir}\n
{lib_include}\n
{add_library}\n
{target_links}
'''.format(proj_name=self._proj_name, cl_flags=cl_flags, check_version=check_version,
           sources=add_library, include_dir=include_dir, add_library=add_library,
           lib_include= lib_include, target_links=target_links, output_dir=output_dir)
        cmake_path = os.path.join(proj_dir, 'CMakeLists.txt')
        with open(cmake_path, 'w') as fd:
            fd.write(cmake_txt)

    def get_output_dir(self):
        code = '''
set(OUT_DIR android_${ANDROID_ABI}/${CMAKE_BUILD_TYPE})
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/../../../${OUT_DIR})
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/../../../${OUT_DIR})
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/../../../${OUT_DIR})
'''
        return code

    def get_add_library(self):
        files = []
        dis_arch = self._support_arch[0]
        for f in self._proj_files:
            path = os.path.join('${CMAKE_CURRENT_LIST_DIR}', f)
            path = path.replace('\\', '/')
            files.append(path)
        sources = '\n\t'.join(files)
        target_type = util.vs_target_to_clang(self._proj_settings[dis_arch]['target_type'])
        code = '''add_library(
    {proj_name}
    {target_type}
    {sources}
)'''.format(proj_name=self._proj_name, target_type=target_type, sources=sources)
        return code

if __name__ == '__main__':
    sln_parser = SlnParser('/mnt/z/xengine/native/libcosmo.sln')
    proj_lst = sln_parser.parse()
    sln_parser.gen_cmake()
    for (name, desc) in proj_lst.items():
        # if name not in ['lua5.3']:
        #     continue
        vcproj_parser = VcProjectParser(desc)
        vcproj_parser.parse()
        vcproj_parser.gen_cmake()
