#!/usr/bin/env python3
# BSD 3-Clause License
# 
# Copyright (c) 2021, Hubert Schreier
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
# 
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
import argparse
from io import open
import sys
import math
import numpy as np
import svgwrite

def bspl_kern(x):
    '''Cubic B-spline kernel and first derivative kernel'''
    a = 0.5 * x
    b = a * x
    c = b * x
    k3 = c / 3;
    k2 = 1/6 + a + b - c
    k1 = 2/3 - b - b + c
    k0 = 1/6 - a + b - k3

    x2 = x * x

    d0 = ( 0.5 * (-1 - x2) + x)
    d1 = (3. * x2 / 2. - 2. * x)
    d2 = ((1. - 3. * x2) / 2. + x)
    d3 = b

    return [ k0, k1, k2, k3], [d0, d1, d2, d3]

def ease_linear(x):
    return x

# I am not sure how useful this is and have not made a cam that has a
# non-linear displacement.
def ease_quad(x):
    return 2 * x - x * x

def deg2rad(x):
    return x / 180.0 * math.pi

def rad2deg(x):
    return x * 180.0 / math.pi

def fit_cam(min_angle, max_angle, r_base, disp, n_seg = 12, n_samp_per_seg = 50, ease_func = ease_linear):
    a_min = deg2rad(min_angle)
    a_max = deg2rad(max_angle)
    n_samp_total = n_seg * n_samp_per_seg
    n_par = 2 * (n_seg + 3)
    y_coeff_off = n_seg + 3
    
    A = np.zeros([2 * n_samp_total, n_par])
    B = np.zeros([2 * n_samp_total])
    
    n_inv_seg = 1.0 / n_samp_per_seg
    n_inv_ang = 1.0 / (n_samp_total - 1)

    # The spline coefficients are determined using a linear least
    # squares method. The cam pushes against a vertical wall. For a
    # given cam rotation angle, the distance from the cam's center
    # point to that wall is the x-coordinate of the spline and should
    # be equal to the prescribed cam displacement in a least-squares
    # sense. The second constraint is on the derivative of the
    # spline. Since the wall is vertical, the derivative in x must be
    # zero, i.e., the cam tangent must be parallel to the wall.
    idx = 0
    for seg in range(n_seg):
        for i in range(n_samp_per_seg):
            q = n_inv_ang * idx
            qq = ease_func(q)
            t = n_inv_seg * i
    
            k, d = bspl_kern(t)
    
            theta = a_min + q * (a_max - a_min)
            c = math.cos(theta)
            s = math.sin(theta)
            h = r_base + disp * qq

            # Displacement constraint
            for j in range(4):
                A[2 * idx, seg + j] = c * k[j]
                A[2 * idx, y_coeff_off + seg + j] = s * k[j]
            B[2 * idx] = h
            # Constraint on the slope, i.e., the derivative in x
            # must be zero
            for j in range(4):
                A[2 * idx + 1, seg + j] = c * d[j]
                A[2 * idx + 1, y_coeff_off + seg + j] = s * d[j]
            B[2 * idx + 1] = 0
            idx += 1

    # Solve equation system
    B = np.linalg.lstsq(A, B, rcond=-1)[0]
            
    C = B.reshape([2, n_seg + 3]).T

    # Evaluate the error and compute friction coefficient required for
    # the cam to lock. The clamping force generated by the cam is
    # orthogonal to the wall the cam pushes on and generates a moment
    # around the cam's rotation axis equal to the force F multiplied
    # by the y-coordinate. For the cam to lock, the friction force
    # must be high enough to generate a corresponding moment μ*F*x,
    # i.e., μ >= y/x.
    err = 0.0
    idx = 0

    cam_pts = np.zeros([n_samp_total, 2])
    friction = np.zeros([n_samp_total, 2])
    for seg in range(n_seg):
        for i in range(n_samp_per_seg):
            q = n_inv_ang * idx
            qq = ease_func(q)
            t = n_inv_seg * i
    
            k, d = bspl_kern(t)
    
            theta = a_min + q * (a_max - a_min)
            c = math.cos(theta)
            s = math.sin(theta)
            h = r_base + disp * qq
    
            x = 0
            y = 0
            p = [0, 0]
            for j in range(4):
                p += k[j] * C[seg+j]

            cam_pts[idx] = p
            
            x = p[0]
            y = p[1]
            x1 = c * x + s * y
            y1 = -s * x + c * y
            err += (h - x1) * (h - x1)
            f = y1 / x1

            friction[idx] = [rad2deg(theta), f]
            idx += 1

    err = math.sqrt(err / n_samp_total)
    return C, err, cam_pts, friction

def spl2bez(B, scale = 1.0):
    '''This function converts a cubic B-spline to a Bezier curve'''
    Q = []
    for i in range(B.shape[0] - 3):
        q = np.zeros([4, 2])
        c = [ scale * B[i+j] for j in range(4) ]
        # Gather powers to obtain q0 + q1 * t + q2 * t^2 + q3 * t^3
        q[0] =  c[0] / 6.0 + 2.0 * c[1] / 3.0 + c[2] / 6.0
        q[1] = -c[0] / 2.0 + c[2] / 2.0
        q[2] =  c[0] / 2.0 - c[1] + c[2] / 2.0
        q[3] = -c[0] / 6.0 + c[1] / 2.0 - c[2] / 2.0 + c[3] / 6.0
        # Convert to bezier using binomial coefficients
        c[0] = q[0]
        c[1] = q[0] + 1.0 / 3.0 * q[1]
        c[2] = q[0] + 2.0 / 3.0 * q[1] + 1.0 / 3.0 * q[2]
        c[3] = q[0] + q[1] + q[2] + q[3]
        if not i:
            Q.append(c[0])
        Q.append(c[1])
        Q.append(c[2])
        Q.append(c[3])
    return Q

__desc__ = '''This program computes a cam shape for a given base
radius, displacement and range of rotation angles.'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__desc__)
    parser.add_argument('output', metavar='output.svg',
                            help='Output file.')
    parser.add_argument('--start-angle', '-s', dest='a_min', type=float, default=0.0,
                            help='Start angle of the cam.')
    parser.add_argument('--end-angle', '-e', dest='a_max', type=float, default=120.0,
                            help='End angle of the cam.')
    parser.add_argument('--displacement', '-d', dest='disp', type=float, default=0.5,
                            help='Displacement of the cam.')
    parser.add_argument('--radius', '-r', dest='rad', type=float, default=1.0,
                            help='Base radius of the cam.')
    parser.add_argument('--segments', type=int, default = 12, help='Number of B-spline segments')
    parser.add_argument('--samples', type=int, default = 50, help='Number of sample points per segment')
    parser.add_argument('--quadratic', '-q', default=False, action='store_true',
                            help='Increase displacement as a quadratic function in cam angle (experimental)')
    parser.add_argument('--pts', '-p', dest='pts', help='Save points to file.')
    parser.add_argument('--friction', '-f', dest='friction', help='Save friction coefficient required for cam to lock as a function of angle.')

    args = parser.parse_args()

    ease_func = ease_linear
    if args.quadratic:
        ease_func = ease_quad

    n_seg  = args.segments
    n_samp = args.samples
    
    C, err, pts, friction = fit_cam(args.a_min, args.a_max, args.rad, args.disp, n_seg, n_samp, ease_func)

    # DPI for the svg
    dpi = 96.0
    # Offset 
    ox = 4.25 * dpi
    oy = 5.5 * dpi
    
    Q = spl2bez(C, dpi)
    print("RMS error: {}".format(err), file=sys.stderr)

    if args.pts:
        f = open(args.pts, 'w')
        for p in pts:
            print('{} {}'.format(p[0], p[1]), file=f)
        f.close()
    
    if args.friction:
        f = open(args.friction, 'w')
        for p in friction:
            print('{} {}'.format(p[0], p[1]), file=f)
        f.close()

    if len(Q):
        p = 'M{},{}'.format(ox + Q[0][0], oy - Q[0][1])
        for i in range(1, len(Q), 3):
            p += ' C{},{}, {},{}, {}, {}'.format(ox + Q[i][0], oy - Q[i][1],
                                                   ox + Q[i+1][0], oy- Q[i+1][1],
                                                   ox + Q[i+2][0], oy - Q[i+2][1])
        svg = svgwrite.Drawing(args.output, profile='full', size=(8.5*svgwrite.inch, 11*svgwrite.inch))
        svg.add(svg.path( d=p, stroke=svgwrite.rgb(0, 0, 0, '%'),
                              fill='none',
                              stroke_width=0.7 * svgwrite.mm))
        svg.add(svg.line((ox - 0.125 * dpi, oy), (ox + 0.125 * dpi, oy), stroke=svgwrite.rgb(0, 0, 0, '%'),
                              fill='none',
                              stroke_width=0.7 * svgwrite.mm))
        svg.add(svg.line((ox, oy - 0.125 * dpi), (ox, oy + 0.125 * dpi), stroke=svgwrite.rgb(0, 0, 0, '%'),
                              fill='none',
                              stroke_width=0.7 * svgwrite.mm))
        svg.add(svg.text('Base radius: {}'.format(args.rad),
                             insert=(0.75 * dpi, 0.75 * dpi ),
                             stroke='none',
                             fill='#000',
                             font_size='12pt',
                             font_weight="normal",
                             font_family="Arial")
                    )
        svg.add(svg.text('Displacement: {}'.format(args.disp),
                             insert=(0.75 * dpi, 1.0 * dpi ),
                             stroke='none',
                             fill='#000',
                             font_size='12pt',
                             font_weight="normal",
                             font_family="Arial")
                    )
        svg.add(svg.text('Angle min: {}, max: {}'.format(args.a_min, args.a_max),
                             insert=(0.75 * dpi, 1.25 * dpi ),
                             stroke='none',
                             fill='#000',
                             font_size='12pt',
                             font_weight="normal",
                             font_family="Arial")
                    )
        svg.save()
