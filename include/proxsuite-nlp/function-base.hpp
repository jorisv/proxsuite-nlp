/// @file
/// @copyright Copyright (C) 2022 LAAS-CNRS, INRIA
/// @brief     Base definitions for function classes.
#pragma once

#include "proxsuite-nlp/fwd.hpp"

namespace proxsuite {
namespace nlp {
/**
 * @brief Base function type.
 */
template <typename _Scalar> struct BaseFunctionTpl : math_types<_Scalar> {
protected:
  int nx_;
  int ndx_;
  int nr_;

public:
  using Scalar = _Scalar;
  PROXSUITE_NLP_DYNAMIC_TYPEDEFS(Scalar);

  BaseFunctionTpl(const int nx, const int ndx, const int nr)
      : nx_(nx), ndx_(ndx), nr_(nr) {}

  BaseFunctionTpl(const ManifoldAbstractTpl<Scalar> &manifold, const int nr)
      : BaseFunctionTpl(manifold.nx(), manifold.ndx(), nr) {}

  /// @brief      Evaluate the residual at a given point x.
  virtual VectorXs operator()(const ConstVectorRef &x) const = 0;

  virtual ~BaseFunctionTpl() = default;

  /// Get function input vector size (representation of manifold).
  int nx() const { return nx_; }
  /// Get input manifold's tangent space dimension.
  int ndx() const { return ndx_; }
  /// Get function codimension.
  int nr() const { return nr_; }
};

/** @brief  Differentiable function, with method for the Jacobian.
 */
template <typename _Scalar>
struct C1FunctionTpl : public BaseFunctionTpl<_Scalar> {
public:
  using Scalar = _Scalar;
  using Base = BaseFunctionTpl<_Scalar>;
  using Base::Base;
  PROXSUITE_NLP_DYNAMIC_TYPEDEFS(Scalar);

  /// @brief      Jacobian matrix of the constraint function.
  virtual void computeJacobian(const ConstVectorRef &x,
                               MatrixRef Jout) const = 0;

  /** @copybrief computeJacobian()
   *
   * Allocated version of the computeJacobian() method.
   */
  MatrixXs computeJacobian(const ConstVectorRef &x) const {
    MatrixXs Jout(this->nr(), this->ndx());
    computeJacobian(x, Jout);
    return Jout;
  }
};

/** @brief  Twice-differentiable function, with method Jacobian and
 * vector-hessian product evaluation.
 */
template <typename _Scalar>
struct C2FunctionTpl : public C1FunctionTpl<_Scalar> {
public:
  using Scalar = _Scalar;
  using Base = C1FunctionTpl<_Scalar>;
  using Base::Base;
  PROXSUITE_NLP_DYNAMIC_TYPEDEFS(Scalar);

  /// @brief      Vector-hessian product.
  virtual void vectorHessianProduct(const ConstVectorRef &,
                                    const ConstVectorRef &,
                                    MatrixRef Hout) const {
    Hout.setZero();
  }
};

} // namespace nlp
} // namespace proxsuite

#ifdef PROXSUITE_NLP_ENABLE_TEMPLATE_INSTANTIATION
#include "proxsuite-nlp/function-base.txx"
#endif
