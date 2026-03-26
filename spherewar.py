#!/usr/bin/env python3
"""
SphereWar - Single-player: hunt generated enemies on a tiny sphere!

Controls:
  WASD / Arrow Keys  - Turn and move
  Space / F          - Throw spear
  ESC                - Quit

Requires: pip install pygame
"""

import pygame
import sys
import math
import random
from typing import Dict, List, Tuple

# ─── Constants ────────────────────────────────────────────────────────────────

WIDTH, HEIGHT = 960, 720
FPS = 60

SPHERE_RADIUS = 220
SCX, SCY = WIDTH // 2, HEIGHT // 2 - 10

PLAYER_SPEED   = 0.028
TURN_SPEED     = 0.075
SPEAR_SPEED    = 0.045
SPEAR_LIFETIME = 160
SPEAR_ARC      = 0.45
HIT_ANGLE      = 0.16
THROW_COOLDOWN = 75

ENEMY_SPEED     = 0.008
ENEMY_TURN_RATE = 0.045
NUM_ENEMIES     = 8
ENEMY_HEALTH    = 2
ENEMY_RESPAWN   = 240

CAM_TILT = math.radians(28)

PLAYER_COLOR = (235, 80, 80)
ENEMY_COLORS = [
    (200, 130,  40),
    (140,  80, 210),
    ( 50, 190, 180),
    (210, 190,  50),
    (180,  80, 130),
    ( 90, 180,  90),
    (210,  90,  90),
    ( 90, 130, 210),
]

# ─── Camera ───────────────────────────────────────────────────────────────────

_cam_theta = 0.0
_cam_phi   = math.pi / 2
_cam_rot_y = 0.0


def tangent_basis(theta: float, phi: float):
    cp, sp = math.cos(phi), math.sin(phi)
    ct, st = math.cos(theta), math.sin(theta)
    e_phi   = ( cp*ct, -sp, cp*st)
    e_theta = (-st,     0,  ct   )
    return e_phi, e_theta


def set_camera(theta: float, phi: float, facing: float):
    global _cam_theta, _cam_phi, _cam_rot_y
    _cam_theta, _cam_phi = theta, phi

    # Transform player's facing vector through the first two rotations
    # to determine the third rotation that aligns facing with screen-up.
    e_phi, e_theta = tangent_basis(theta, phi)
    cd, sd = math.cos(facing), math.sin(facing)
    fx = cd*e_phi[0] + sd*e_theta[0]
    fy = cd*e_phi[1] + sd*e_theta[1]
    fz = cd*e_phi[2] + sd*e_theta[2]

    # rotY(-theta): x' = cos(t)*x + sin(t)*z,  z' = -sin(t)*x + cos(t)*z
    ct, st = math.cos(theta), math.sin(theta)
    fx1 = ct*fx + st*fz
    fy1 = fy
    fz1 = -st*fx + ct*fz

    # rotZ(phi)
    cp, sp = math.cos(phi), math.sin(phi)
    fx2 = cp*fx1 - sp*fy1
    fz2 = fz1

    # Angle to rotate around Y so facing maps to (0, 0, -1) = screen-up
    _cam_rot_y = math.atan2(-fx2, -fz2)


def apply_camera(x: float, y: float, z: float) -> Tuple[float, float, float]:
    """Rotate world so player is at top of sphere, facing upward on screen."""
    # rotY(-theta): x' = cos(t)*x + sin(t)*z,  z' = -sin(t)*x + cos(t)*z
    ct, st = math.cos(_cam_theta), math.sin(_cam_theta)
    x1 = ct*x + st*z
    y1 = y
    z1 = -st*x + ct*z

    # rotZ(phi)
    cp, sp = math.cos(_cam_phi), math.sin(_cam_phi)
    x2 = cp*x1 - sp*y1
    y2 = sp*x1 + cp*y1
    z2 = z1

    # rotY(_cam_rot_y): x' = cos(r)*x - sin(r)*z,  z' = sin(r)*x + cos(r)*z
    cr, sr = math.cos(_cam_rot_y), math.sin(_cam_rot_y)
    x3 = cr*x2 - sr*z2
    y3 = y2
    z3 = sr*x2 + cr*z2
    return x3, y3, z3


# ─── Math helpers ─────────────────────────────────────────────────────────────

def sph2cart(theta: float, phi: float) -> Tuple[float, float, float]:
    return (
        math.sin(phi) * math.cos(theta),
        math.cos(phi),
        math.sin(phi) * math.sin(theta),
    )

def cart2sph(x, y, z) -> Tuple[float, float]:
    phi = math.acos(max(-1.0, min(1.0, y)))
    theta = math.atan2(z, x) % (2 * math.pi)
    return theta, phi

def dot3(a, b):
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]

def angular_dist(t1, p1, t2, p2) -> float:
    return math.acos(max(-1.0, min(1.0, dot3(sph2cart(t1, p1), sph2cart(t2, p2)))))

def move_on_sphere(theta, phi, direction, distance) -> Tuple[float, float]:
    pos = sph2cart(theta, phi)
    e_phi, e_theta = tangent_basis(theta, phi)
    cd, sd = math.cos(direction), math.sin(direction)
    fwd = (
        cd * e_phi[0] + sd * e_theta[0],
        cd * e_phi[1] + sd * e_theta[1],
        cd * e_phi[2] + sd * e_theta[2],
    )
    cd2, sd2 = math.cos(distance), math.sin(distance)
    nx = pos[0]*cd2 + fwd[0]*sd2
    ny = pos[1]*cd2 + fwd[1]*sd2
    nz = pos[2]*cd2 + fwd[2]*sd2
    mag = math.sqrt(nx*nx + ny*ny + nz*nz)
    return cart2sph(nx/mag, ny/mag, nz/mag)


# ─── 3-D → Screen projection ──────────────────────────────────────────────────

def project(x, y, z) -> Tuple[float, float, float]:
    ry = y * math.cos(CAM_TILT) - z * math.sin(CAM_TILT)
    rz = y * math.sin(CAM_TILT) + z * math.cos(CAM_TILT)
    sx = SCX + x * SPHERE_RADIUS
    sy = SCY - ry * SPHERE_RADIUS
    return sx, sy, rz

def sph_to_screen(theta, phi, radial_scale=1.0):
    x, y, z = sph2cart(theta, phi)
    return project(*apply_camera(x * radial_scale, y * radial_scale, z * radial_scale))

def direction_on_screen(theta, phi, facing):
    e_phi, e_theta = tangent_basis(theta, phi)
    cd, sd = math.cos(facing), math.sin(facing)
    x, y, z = sph2cart(theta, phi)
    dx = cd*e_phi[0] + sd*e_theta[0]
    dy = cd*e_phi[1] + sd*e_theta[1]
    dz = cd*e_phi[2] + sd*e_theta[2]
    tip = 0.18
    sx0, sy0, _ = sph_to_screen(theta, phi)
    sx1, sy1, _ = project(*apply_camera(x + dx*tip, y + dy*tip, z + dz*tip))
    ddx, ddy = sx1 - sx0, sy1 - sy0
    mag = math.sqrt(ddx*ddx + ddy*ddy)
    if mag < 0.01:
        return 1.0, 0.0
    return ddx/mag, ddy/mag


# ─── Game objects ─────────────────────────────────────────────────────────────

class Player:
    def __init__(self):
        self.theta  = random.uniform(0, 2*math.pi)
        self.phi    = random.uniform(0.5, math.pi - 0.5)
        self.facing = random.uniform(0, 2*math.pi)
        self.score  = 0
        self.last_throw = -(THROW_COOLDOWN + 1)


class Enemy:
    def __init__(self, eid: int):
        self.eid         = eid
        self.color       = ENEMY_COLORS[eid % len(ENEMY_COLORS)]
        self.alive       = True
        self.health      = ENEMY_HEALTH
        self.death_frame = -(ENEMY_RESPAWN + 1)
        self._turn_timer = random.randint(20, 80)
        self._turn_dir   = random.uniform(-1, 1)
        self.theta  = random.uniform(0, 2*math.pi)
        self.phi    = random.uniform(0.4, math.pi - 0.4)
        self.facing = random.uniform(0, 2*math.pi)

    def update(self, frame: int):
        if not self.alive:
            if frame - self.death_frame >= ENEMY_RESPAWN:
                self.theta  = random.uniform(0, 2*math.pi)
                self.phi    = random.uniform(0.4, math.pi - 0.4)
                self.facing = random.uniform(0, 2*math.pi)
                self.health = ENEMY_HEALTH
                self.alive  = True
            return
        self._turn_timer -= 1
        if self._turn_timer <= 0:
            self._turn_timer = random.randint(30, 100)
            self._turn_dir   = random.uniform(-1, 1)
        self.facing = (self.facing + self._turn_dir * ENEMY_TURN_RATE) % (2 * math.pi)
        self.theta, self.phi = move_on_sphere(
            self.theta, self.phi, self.facing, ENEMY_SPEED)


class Spear:
    def __init__(self, sid: int, theta: float, phi: float, direction: float):
        self.sid       = sid
        self.theta     = theta
        self.phi       = phi
        self.direction = direction
        self.age       = 0


class Game:
    def __init__(self):
        self.frame   = 0
        self.player  = Player()
        self.enemies: List[Enemy] = [Enemy(i) for i in range(NUM_ENEMIES)]
        self.spears:  Dict[int, Spear] = {}
        self.next_sid = 0

    def throw(self):
        p = self.player
        if self.frame - p.last_throw >= THROW_COOLDOWN:
            p.last_throw = self.frame
            sid = self.next_sid
            self.next_sid += 1
            self.spears[sid] = Spear(sid, p.theta, p.phi, p.facing)

    def update(self):
        self.frame += 1
        for e in self.enemies:
            e.update(self.frame)
        dead: List[int] = []
        for sid, sp in self.spears.items():
            sp.age += 1
            if sp.age > SPEAR_LIFETIME:
                dead.append(sid)
                continue
            sp.theta, sp.phi = move_on_sphere(
                sp.theta, sp.phi, sp.direction, SPEAR_SPEED)
            for e in self.enemies:
                if not e.alive:
                    continue
                if angular_dist(sp.theta, sp.phi, e.theta, e.phi) < HIT_ANGLE:
                    e.health -= 1
                    if e.health <= 0:
                        e.alive = False
                        e.death_frame = self.frame
                        self.player.score += 1
                    dead.append(sid)
                    break
        for sid in dead:
            self.spears.pop(sid, None)


# ─── Drawing ──────────────────────────────────────────────────────────────────

_STARS = None

def get_stars():
    global _STARS
    if _STARS is None:
        rng = random.Random(999)
        _STARS = [(rng.randint(0, WIDTH), rng.randint(0, HEIGHT),
                   rng.randint(130, 255), rng.choice([1, 1, 1, 2]))
                  for _ in range(160)]
    return _STARS


def draw_background(surf):
    surf.fill((14, 20, 42))
    for sx, sy, br, sz in get_stars():
        pygame.draw.circle(surf, (br, br, min(255, br+30)), (sx, sy), sz)


def draw_sphere(surf):
    pygame.draw.circle(surf, (38, 85, 38), (SCX, SCY), SPHERE_RADIUS)
    grid_col = (52, 108, 52)
    for lat in range(-60, 90, 30):
        phi = math.pi/2 - math.radians(lat)
        pts = []
        for lon in range(0, 362, 4):
            sx, sy, depth = sph_to_screen(math.radians(lon), phi)
            if depth > -0.05:
                pts.append((int(sx), int(sy)))
            else:
                if len(pts) >= 2:
                    pygame.draw.lines(surf, grid_col, False, pts, 1)
                pts = []
        if len(pts) >= 2:
            pygame.draw.lines(surf, grid_col, False, pts, 1)
    for lon in range(0, 360, 30):
        theta = math.radians(lon)
        pts = []
        for lat in range(-88, 91, 4):
            phi = math.pi/2 - math.radians(lat)
            sx, sy, depth = sph_to_screen(theta, phi)
            if depth > -0.05:
                pts.append((int(sx), int(sy)))
            else:
                if len(pts) >= 2:
                    pygame.draw.lines(surf, grid_col, False, pts, 1)
                pts = []
        if len(pts) >= 2:
            pygame.draw.lines(surf, grid_col, False, pts, 1)
    pygame.draw.circle(surf, (65, 145, 65), (SCX, SCY), SPHERE_RADIUS, 3)
    hl_r = SPHERE_RADIUS // 5
    hl_x = SCX - SPHERE_RADIUS // 4
    hl_y = SCY - SPHERE_RADIUS // 4
    hl_surf = pygame.Surface((hl_r*2, hl_r*2), pygame.SRCALPHA)
    pygame.draw.circle(hl_surf, (255, 255, 255, 40), (hl_r, hl_r), hl_r)
    surf.blit(hl_surf, (hl_x - hl_r, hl_y - hl_r))


def draw_entity(surf, theta, phi, facing, color, health, is_player, font_sm):
    sx, sy, depth = sph_to_screen(theta, phi)
    if depth < -0.12:
        return
    alpha = min(1.0, (depth + 0.12) / 0.25)
    c      = tuple(int(v * alpha + 20*(1-alpha)) for v in color)
    shadow = tuple(max(0, v - 90) for v in c)
    ix, iy = int(sx), int(sy)

    pygame.draw.ellipse(surf, shadow, (ix-9, iy+5, 18, 7))
    border = (255, 255, 255) if is_player else (20, 20, 20)
    pygame.draw.circle(surf, c, (ix, iy), 10)
    pygame.draw.circle(surf, border, (ix, iy), 10, 2)

    ddx, ddy = direction_on_screen(theta, phi, facing)
    tip_len = 16
    pygame.draw.line(surf, (255, 250, 180),
                     (ix, iy), (int(ix + ddx*tip_len), int(iy + ddy*tip_len)), 2)
    pygame.draw.circle(surf, (255, 230, 80),
                       (int(ix + ddx*tip_len), int(iy + ddy*tip_len)), 3)

    for i in range(max(0, health)):
        hx = ix - (health - 1)*5 + i*10
        pygame.draw.circle(surf, (230, 60, 60), (hx, iy + 16), 4)

    if is_player:
        lbl = font_sm.render("YOU", True, c)
        surf.blit(lbl, (ix - lbl.get_width()//2, iy - 26))


def draw_spear(surf, sp: Spear):
    t = sp.age / SPEAR_LIFETIME
    arc_h = math.sin(t * math.pi) * SPEAR_ARC
    sx, sy, depth = sph_to_screen(sp.theta, sp.phi, 1.0 + arc_h)
    if depth < -0.15:
        return
    ddx, ddy = direction_on_screen(sp.theta, sp.phi, sp.direction)
    shaft = 16
    x1, y1 = int(sx - ddx*shaft/2), int(sy - ddy*shaft/2)
    x2, y2 = int(sx + ddx*shaft/2), int(sy + ddy*shaft/2)
    fade = min(1.0, (depth + 0.15) / 0.2)
    shaft_col  = tuple(int(c * fade) for c in (200, 165, 55))
    tip_col    = tuple(int(c * fade) for c in (240, 230, 60))
    shadow_col = tuple(int(c * fade) for c in (80, 60, 20))
    pygame.draw.line(surf, shadow_col, (x1+1, y1+2), (x2+1, y2+2), 2)
    pygame.draw.line(surf, shaft_col,  (x1,   y1  ), (x2,   y2  ), 3)
    pygame.draw.circle(surf, tip_col, (x2, y2), 3)


def draw_hud(surf, game: Game, cooldown_pct: float, font, font_sm):
    p = game.player
    alive_count = sum(1 for e in game.enemies if e.alive)

    surf.blit(font.render(f"Score: {p.score}", True, (220, 220, 100)), (10, 10))
    surf.blit(font_sm.render(f"Enemies: {alive_count} / {NUM_ENEMIES}", True, (180, 140, 100)), (10, 38))

    bar_w, bar_h = 120, 12
    bx, by = 10, HEIGHT - 45
    pygame.draw.rect(surf, (60, 60, 60), (bx, by, bar_w, bar_h), border_radius=4)
    filled = int(bar_w * cooldown_pct)
    bar_col = (80, 220, 80) if cooldown_pct >= 1.0 else (180, 120, 30)
    if filled > 0:
        pygame.draw.rect(surf, bar_col, (bx, by, filled, bar_h), border_radius=4)
    pygame.draw.rect(surf, (120, 120, 120), (bx, by, bar_w, bar_h), 1, border_radius=4)
    lbl = font_sm.render("THROW" if cooldown_pct >= 1.0 else "reload...", True, bar_col)
    surf.blit(lbl, (bx + bar_w + 6, by - 1))

    hint = "WASD / ↑↓←→  Move & Turn    Space / F  Throw    ESC  Quit"
    lbl = font_sm.render(hint, True, (90, 90, 120))
    surf.blit(lbl, (WIDTH//2 - lbl.get_width()//2, HEIGHT - 22))


# ─── Main game loop ───────────────────────────────────────────────────────────

def run_game():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("SphereWar – Solo Hunt")
    clock = pygame.time.Clock()

    font    = pygame.font.SysFont('Arial', 20, bold=True)
    font_sm = pygame.font.SysFont('Arial', 14)

    game = Game()
    set_camera(game.player.theta, game.player.phi, game.player.facing)

    while True:
        clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
                if event.key in (pygame.K_SPACE, pygame.K_f):
                    game.throw()

        keys = pygame.key.get_pressed()
        p = game.player
        dx = int(keys[pygame.K_RIGHT] or keys[pygame.K_d]) - int(keys[pygame.K_LEFT] or keys[pygame.K_a])
        dy = int(keys[pygame.K_DOWN]  or keys[pygame.K_s]) - int(keys[pygame.K_UP]   or keys[pygame.K_w])
        if dx:
            p.facing = (p.facing + dx * TURN_SPEED) % (2 * math.pi)
        if dy:
            p.theta, p.phi = move_on_sphere(p.theta, p.phi, p.facing, PLAYER_SPEED * -dy)

        game.update()
        set_camera(p.theta, p.phi, p.facing)

        cooldown_pct = min(1.0, (game.frame - p.last_throw) / THROW_COOLDOWN)

        draw_background(screen)
        draw_sphere(screen)

        # Collect drawables and sort far→near
        drawables = []
        for sp in game.spears.values():
            t = sp.age / SPEAR_LIFETIME
            _, _, depth = sph_to_screen(sp.theta, sp.phi, 1 + math.sin(t * math.pi) * SPEAR_ARC)
            drawables.append(('spear', depth, sp))
        for e in game.enemies:
            if e.alive:
                _, _, depth = sph_to_screen(e.theta, e.phi)
                drawables.append(('enemy', depth, e))
        _, _, pdepth = sph_to_screen(p.theta, p.phi)
        drawables.append(('player', pdepth, p))
        drawables.sort(key=lambda d: d[1])

        for kind, _, obj in drawables:
            if kind == 'spear':
                draw_spear(screen, obj)
            elif kind == 'enemy':
                draw_entity(screen, obj.theta, obj.phi, obj.facing,
                            obj.color, obj.health, False, font_sm)
            else:
                draw_entity(screen, obj.theta, obj.phi, obj.facing,
                            PLAYER_COLOR, 3, True, font_sm)

        draw_hud(screen, game, cooldown_pct, font, font_sm)
        pygame.display.flip()


if __name__ == '__main__':
    run_game()
