
#include "proxsuite-nlp/cost-function.hpp"

namespace proxsuite {
namespace nlp {

template struct CostFunctionBaseTpl<context::Scalar>;

template auto downcast_function_to_cost<context::Scalar>(
    const shared_ptr<context::C2Function> &) -> shared_ptr<context::Cost>;

} // namespace nlp
} // namespace proxsuite
