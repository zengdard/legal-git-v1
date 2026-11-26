#pragma once

#include <stdexcept>
#include <string>
#include <utility>

namespace legal_git {

// Error type shared by the whole core. `code` is a stable machine-readable
// identifier (see each module); the message is human-readable detail.
struct CoreError : public std::runtime_error {
  std::string code;

  CoreError(std::string code_, const std::string& message)
      : std::runtime_error(message), code(std::move(code_)) {}
};

}  // namespace legal_git
