"use strict";

/**
 * Lightweight bone/attachment animation runtime for overlay RO paperdoll.
 * Applies CSS transforms to .ov-bone / .ov-attach; clips selected by weapon_type.
 */
(function (global) {
  const CLIPS = {
    idle_breathe: {
      durationMs: 3200,
      loop: true,
      keys: [
        { t: 0, bones: { hip: { ty: 0 }, torso: { ty: 0, rot: 0 }, head: { rot: 0 } } },
        { t: 0.5, bones: { hip: { ty: -2 }, torso: { ty: -1, rot: 0.6 }, head: { rot: -0.8 } } },
        { t: 1, bones: { hip: { ty: 0 }, torso: { ty: 0, rot: 0 }, head: { rot: 0 } } },
      ],
    },
    idle_sway: {
      durationMs: 6000,
      loop: true,
      keys: [
        { t: 0, bones: { root: { rot: -1.2 }, arm_r: { rot: 2 }, arm_l: { rot: -2 } } },
        { t: 0.5, bones: { root: { rot: 1.2 }, arm_r: { rot: -2 }, arm_l: { rot: 2 } } },
        { t: 1, bones: { root: { rot: -1.2 }, arm_r: { rot: 2 }, arm_l: { rot: -2 } } },
      ],
    },
    attack_melee: {
      durationMs: 180,
      loop: false,
      keys: [
        { t: 0, bones: { root: { tx: 0, rot: 0 }, arm_r: { rot: -10 }, torso: { rot: 0 } } },
        { t: 0.45, bones: { root: { tx: 10, rot: 4 }, arm_r: { rot: 35 }, torso: { rot: 6 } } },
        { t: 1, bones: { root: { tx: 0, rot: 0 }, arm_r: { rot: -10 }, torso: { rot: 0 } } },
      ],
    },
    attack_melee_sword: {
      durationMs: 200,
      loop: false,
      keys: [
        { t: 0, bones: { root: { tx: 0 }, arm_r: { rot: -20 }, hand_r: { rot: -15 } } },
        { t: 0.4, bones: { root: { tx: 12 }, arm_r: { rot: 40 }, hand_r: { rot: 25 } } },
        { t: 1, bones: { root: { tx: 0 }, arm_r: { rot: -20 }, hand_r: { rot: -15 } } },
      ],
    },
    attack_melee_dagger: {
      durationMs: 140,
      loop: false,
      keys: [
        { t: 0, bones: { root: { tx: 0 }, arm_r: { rot: -5 } } },
        { t: 0.5, bones: { root: { tx: 14 }, arm_r: { rot: 28 } } },
        { t: 1, bones: { root: { tx: 0 }, arm_r: { rot: -5 } } },
      ],
    },
    attack_melee_axe: {
      durationMs: 220,
      loop: false,
      keys: [
        { t: 0, bones: { root: { tx: 0, rot: -3 }, arm_r: { rot: -40 } } },
        { t: 0.5, bones: { root: { tx: 10, rot: 6 }, arm_r: { rot: 50 } } },
        { t: 1, bones: { root: { tx: 0, rot: -3 }, arm_r: { rot: -40 } } },
      ],
    },
    attack_ranged: {
      durationMs: 220,
      loop: false,
      keys: [
        { t: 0, bones: { arm_r: { rot: -25 }, arm_l: { rot: 15 }, torso: { rot: -2 } } },
        { t: 0.55, bones: { arm_r: { rot: -5 }, arm_l: { rot: -10 }, torso: { rot: 2 } } },
        { t: 1, bones: { arm_r: { rot: -25 }, arm_l: { rot: 15 }, torso: { rot: -2 } } },
      ],
    },
    attack_magic: {
      durationMs: 260,
      loop: false,
      keys: [
        { t: 0, bones: { arm_r: { rot: -30 }, arm_l: { rot: -20 }, head: { rot: 0 } } },
        { t: 0.5, bones: { arm_r: { rot: 15 }, arm_l: { rot: 10 }, head: { rot: -4 } } },
        { t: 1, bones: { arm_r: { rot: -30 }, arm_l: { rot: -20 }, head: { rot: 0 } } },
      ],
    },
    sleep: {
      durationMs: 4000,
      loop: true,
      keys: [
        { t: 0, bones: { torso: { rot: 2, ty: 1 }, head: { rot: 6 } } },
        { t: 0.5, bones: { torso: { rot: 3, ty: 0 }, head: { rot: 8 } } },
        { t: 1, bones: { torso: { rot: 2, ty: 1 }, head: { rot: 6 } } },
      ],
    },
    dead: {
      durationMs: 1,
      loop: false,
      keys: [{ t: 0, bones: { root: { rot: 12, ty: 8 }, head: { rot: 18 } } }],
    },
  };

  const BONE_NAMES = ["root", "hip", "torso", "head", "arm_r", "arm_l"];
  const ATTACH_NAMES = ["hand_r", "hand_l"];

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  function sampleKeys(keys, t01) {
    if (!keys || !keys.length) return {};
    if (t01 <= keys[0].t) return keys[0].bones || {};
    if (t01 >= keys[keys.length - 1].t) return keys[keys.length - 1].bones || {};
    let i = 0;
    while (i < keys.length - 1 && keys[i + 1].t < t01) i += 1;
    const a = keys[i];
    const b = keys[i + 1];
    const span = b.t - a.t || 1;
    const u = (t01 - a.t) / span;
    const out = {};
    const names = new Set([
      ...Object.keys(a.bones || {}),
      ...Object.keys(b.bones || {}),
    ]);
    names.forEach((name) => {
      const pa = (a.bones && a.bones[name]) || {};
      const pb = (b.bones && b.bones[name]) || {};
      out[name] = {
        tx: lerp(pa.tx || 0, pb.tx || 0, u),
        ty: lerp(pa.ty || 0, pb.ty || 0, u),
        rot: lerp(pa.rot || 0, pb.rot || 0, u),
        sx: lerp(pa.sx != null ? pa.sx : 1, pb.sx != null ? pb.sx : 1, u),
        sy: lerp(pa.sy != null ? pa.sy : 1, pb.sy != null ? pb.sy : 1, u),
      };
    });
    return out;
  }

  function applyPose(rootEl, pose) {
    if (!rootEl || !pose) return;
    BONE_NAMES.forEach((name) => {
      const node = rootEl.querySelector(`.ov-bone[data-bone="${name}"]`);
      if (!node) return;
      const p = pose[name] || { tx: 0, ty: 0, rot: 0, sx: 1, sy: 1 };
      node.style.transform = `translate(${p.tx || 0}px, ${p.ty || 0}px) rotate(${p.rot || 0}deg) scale(${p.sx != null ? p.sx : 1}, ${p.sy != null ? p.sy : 1})`;
    });
    ATTACH_NAMES.forEach((name) => {
      const node = rootEl.querySelector(`.ov-attach[data-attach="${name}"]`);
      if (!node) return;
      const p = pose[name] || { tx: 0, ty: 0, rot: 0, sx: 1, sy: 1 };
      node.style.transform = `translate(${p.tx || 0}px, ${p.ty || 0}px) rotate(${p.rot || 0}deg) scale(${p.sx != null ? p.sx : 1}, ${p.sy != null ? p.sy : 1})`;
    });
  }

  function resetPose(rootEl) {
    if (!rootEl) return;
    rootEl.querySelectorAll(".ov-bone, .ov-attach").forEach((node) => {
      node.style.transform = "";
    });
  }

  function pickAttackClip(attackType, weaponType) {
    const at = (attackType || "melee").toLowerCase();
    const wt = (weaponType || "unarmed").toLowerCase();
    if (at === "ranged") return "attack_ranged";
    if (at === "magic") return "attack_magic";
    const keyed = `attack_melee_${wt}`;
    if (CLIPS[keyed]) return keyed;
    return "attack_melee";
  }

  function createRuntime(rootEl) {
    let raf = null;
    let idleClipId = "idle_breathe";
    let idleStart = performance.now();
    let oneshot = null;

    function tick(now) {
      raf = requestAnimationFrame(tick);
      if (!rootEl || !rootEl.isConnected) return;

      let pose = {};
      if (oneshot) {
        const elapsed = now - oneshot.start;
        const t01 = Math.min(1, elapsed / oneshot.durationMs);
        pose = sampleKeys(oneshot.keys, t01);
        if (t01 >= 1) oneshot = null;
      } else {
        const clip = CLIPS[idleClipId] || CLIPS.idle_breathe;
        const dur = clip.durationMs || 3000;
        const t01 = ((now - idleStart) % dur) / dur;
        pose = sampleKeys(clip.keys, t01);
      }
      applyPose(rootEl, pose);
    }

    function start() {
      if (raf) return;
      idleStart = performance.now();
      raf = requestAnimationFrame(tick);
    }

    function stop() {
      if (raf) cancelAnimationFrame(raf);
      raf = null;
      oneshot = null;
      resetPose(rootEl);
    }

    function setIdleClip(id) {
      idleClipId = CLIPS[id] ? id : "idle_breathe";
      idleStart = performance.now();
    }

    function playAttack(attackType, weaponType) {
      const id = pickAttackClip(attackType, weaponType);
      const clip = CLIPS[id] || CLIPS.attack_melee;
      oneshot = {
        keys: clip.keys,
        durationMs: clip.durationMs || 200,
        start: performance.now(),
      };
    }

    function setMode(mode) {
      if (mode === "sleep" || mode === "sleep_dungeon") setIdleClip("sleep");
      else if (mode === "dead") {
        setIdleClip("dead");
        applyPose(rootEl, sampleKeys(CLIPS.dead.keys, 0));
      } else if (mode === "battle") setIdleClip("idle_breathe");
      else setIdleClip("idle_sway");
    }

    return { start, stop, setIdleClip, playAttack, setMode, pickAttackClip };
  }

  global.RoPaperdollSkeleton = {
    CLIPS,
    pickAttackClip,
    createRuntime,
    applyPose,
    resetPose,
  };
})(typeof window !== "undefined" ? window : globalThis);
