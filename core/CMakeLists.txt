cmake_minimum_required(VERSION 3.25)
project(legal_git_core VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(LEGALGIT_BUILD_TESTS "Build GoogleTest suite" ON)
option(LEGALGIT_BUILD_PYTHON "Build the pybind11 module for the FastAPI layer" ON)

include(FetchContent)

FetchContent_Declare(
  pugixml
  GIT_REPOSITORY https://github.com/zeux/pugixml.git
  GIT_TAG v1.14
)
FetchContent_MakeAvailable(pugixml)

FetchContent_Declare(
  nlohmann_json
  GIT_REPOSITORY https://github.com/nlohmann/json.git
  GIT_TAG v3.11.3
)
FetchContent_MakeAvailable(nlohmann_json)

add_library(legal_git_core STATIC
  src/sha256.cpp
  src/utf8.cpp
  src/diff.cpp
  src/fragment.cpp
  src/ids.cpp
  src/xml_corpus.cpp
  src/legi.cpp
)
target_include_directories(legal_git_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_link_libraries(legal_git_core PUBLIC pugixml::pugixml nlohmann_json::nlohmann_json)
# The static core links into the pybind11 shared module.
set_target_properties(legal_git_core PROPERTIES POSITION_INDEPENDENT_CODE ON)

if(LEGALGIT_BUILD_TESTS)
  FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG v1.15.2
  )
  set(gtest_force_shared_crt ON)
  FetchContent_MakeAvailable(googletest)

  enable_testing()
  add_executable(core_tests
    tests/test_sha256.cpp
    tests/test_utf8.cpp
    tests/test_diff.cpp
    tests/test_fragment.cpp
    tests/test_ids.cpp
    tests/test_xml.cpp
    tests/test_legi.cpp
    tests/test_fidelity.cpp
  )
  target_link_libraries(core_tests PRIVATE legal_git_core GTest::gtest_main)
  include(GoogleTest)
  gtest_discover_tests(core_tests)
endif()

if(LEGALGIT_BUILD_PYTHON)
  # pybind11 master tracks the latest CPython releases (needed for 3.15).
  FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG master
  )
  FetchContent_MakeAvailable(pybind11)

  pybind11_add_module(legalgit_module MODULE pybind/module.cpp)
  target_link_libraries(legalgit_module PRIVATE legal_git_core)
  # Module is imported by the Python app as `legalgit_core.<abi>.so`,
  # placed next to the `app` package.
  set_target_properties(legalgit_module PROPERTIES
    OUTPUT_NAME legalgit_core
    LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/../app
  )
endif()
