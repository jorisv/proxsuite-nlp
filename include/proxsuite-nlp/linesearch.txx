#pragma once

#include "proxsuite-nlp/context.hpp"
#include "proxsuite-nlp/linesearch-base.hpp"

namespace proxsuite {
namespace nlp {

extern template class Linesearch<context::Scalar>;
extern template struct PolynomialTpl<context::Scalar>;
extern template class ArmijoLinesearch<context::Scalar>;

} // namespace nlp
} // namespace proxsuite
