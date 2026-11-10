# Writes build-info-facts.json at configure time and BUILD-INFO.json at build time
# (scripts/gen-build-info.py), and installs the manifest at the prefix root.
macro(SetupBuildInfo)
    # OCCT version, with the development suffix (e.g. "rc4-e72d772e70") when defined
    set(BUILD_INFO_OCC "${OCC_VERSION_STRING}")
    if(OCC_VERSION_DEVELOPMENT)
        string(APPEND BUILD_INFO_OCC ".${OCC_VERSION_DEVELOPMENT}")
    endif()

    # Sorted JSON array of every enabled BUILD_X module. X is mapped to the matching
    # src/Mod directory name (PART_DESIGN -> PartDesign); unmatched names are kept as is.
    file(GLOB _bi_mod_dirs LIST_DIRECTORIES true RELATIVE ${CMAKE_SOURCE_DIR}/src/Mod
         ${CMAKE_SOURCE_DIR}/src/Mod/*)
    foreach(_bi_dir ${_bi_mod_dirs})
        string(TOUPPER "${_bi_dir}" _bi_dir_key)
        set(_bi_dirmap_${_bi_dir_key} "${_bi_dir}")
    endforeach()
    get_cmake_property(_bi_vars CACHE_VARIABLES)
    set(_bi_modules "")
    foreach(_bi_var ${_bi_vars})
        if(_bi_var MATCHES "^BUILD_(.+)$")
            set(_bi_name "${CMAKE_MATCH_1}")
            if(${_bi_var} AND NOT _bi_name MATCHES "^(GUI|TEST|DYNAMIC_LINK_PYTHON)$")
                string(REPLACE "_" "" _bi_key "${_bi_name}")
                if(DEFINED _bi_dirmap_${_bi_key})
                    list(APPEND _bi_modules "${_bi_dirmap_${_bi_key}}")
                else()
                    list(APPEND _bi_modules "${_bi_name}")
                endif()
            endif()
        endif()
    endforeach()
    list(SORT _bi_modules)
    set(BUILD_INFO_MODULES_JSON "[")
    set(_bi_sep "")
    foreach(_bi_mod ${_bi_modules})
        string(APPEND BUILD_INFO_MODULES_JSON "${_bi_sep}\"${_bi_mod}\"")
        set(_bi_sep ", ")
    endforeach()
    string(APPEND BUILD_INFO_MODULES_JSON "]")

    # Selected flags as {"NAME": "ON"|"OFF"}
    set(BUILD_INFO_FLAGS_JSON "{")
    set(_bi_sep "")
    foreach(_bi_flag BUILD_GUI OCCT_CMAKE_FALLBACK ENABLE_DEVELOPER_TESTS FREECAD_VERSION_INCLUDE_GIT)
        if(${_bi_flag})
            set(_bi_val "ON")
        else()
            set(_bi_val "OFF")
        endif()
        string(APPEND BUILD_INFO_FLAGS_JSON "${_bi_sep}\"${_bi_flag}\": \"${_bi_val}\"")
        set(_bi_sep ", ")
    endforeach()
    string(APPEND BUILD_INFO_FLAGS_JSON "}")

    # SDK name: basename of CMAKE_OSX_SYSROOT, JSON null when empty
    if(CMAKE_OSX_SYSROOT)
        get_filename_component(_bi_sdk "${CMAKE_OSX_SYSROOT}" NAME)
        set(BUILD_INFO_SDK "\"${_bi_sdk}\"")
    else()
        set(BUILD_INFO_SDK "null")
    endif()

    configure_file(${CMAKE_SOURCE_DIR}/cMake/build-info-facts.json.in
                   ${CMAKE_BINARY_DIR}/build-info-facts.json @ONLY)

    add_custom_target(fc_build_info ALL
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/scripts/gen-build-info.py
                --srcdir ${CMAKE_SOURCE_DIR}
                --facts ${CMAKE_BINARY_DIR}/build-info-facts.json
                --out ${CMAKE_BINARY_DIR}/BUILD-INFO.json
        VERBATIM)

    install(FILES ${CMAKE_BINARY_DIR}/BUILD-INFO.json DESTINATION .)
endmacro(SetupBuildInfo)
