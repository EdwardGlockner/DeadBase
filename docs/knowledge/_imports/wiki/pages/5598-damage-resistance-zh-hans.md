# Damage Resistance/zh-hans

Imported reference

- kind: pages
- source: Deadlock Wiki
- url: https://deadlock.wiki/Damage_Resistance/zh-hans
- imported_at: 2026-07-10T07:07:40+00:00

Reference extract:

Damage Resistance refers to the Bullet, Melee, and Spirit Resist statistics which reduce incoming damage taken. Bullet Resist reduces all weapon and melee damage, Melee Resist reduces only melee damage, while Spirit Resist reduces all spirit damage.

Most resistances stack diminishingly, with each additional resistance source having reduced effect. Resistance Reduction is applied to the final resistance, and is stacked separately and diminishingly.

The Bullet Resistance and Spirit Resistance stats are also sometimes referred to as "Bullet Armor" and "Spirit Armor".

### Boon Resistances

Resistances gained from Boons (e.g., Dynamo's Bullet Resist or Kelvin's Spirit Resist) stack additively (1% per Boon, up to 20%). This is an exception to the standard multiplicative stacking rules for other resist sources.

## Melee Resist

Melee Resist is a special case of Bullet Resist that stacks diminishingly alongside it to reduce all incoming melee damage. This includes all 'melee' abilities such as 魔液' 绿水神拳 ability.

## Math

Despite being presented in-game as +x% Bullet, Melee, or Spirit Resist, multiple sources of resist stack multiplicatively, not additively.

The formula for resist is: BRf=⌈1−∏i=1n(1−BRi)⌉ where: BRf=final bullet resist,n=number of bullet resist sources,BRn=bullet resist value

For example, multiple sources of Bullet Resist:

- 60% Bullet Resist from Viscous' Goo Ball

- 40% Bullet Resist from the Colossus Item results in:

1−(1−0.6)*(1−0.4)=76% Bullet Resist

## Resistance Reduction

Resistance Reduction refers to any negative amount of Resist, making the target take increased damage.

Resistance Reduction is calculated multiplicatively like resistance, but then simply subtracted from the resistance amount.

𝐷𝑖𝑠𝑝𝑙𝑎𝑦𝑒𝑑𝑅𝑒𝑠𝑖𝑠𝑡=[1−(1−𝑅𝑒𝑠𝑖𝑠𝑡𝑎𝑛𝑐𝑒1)*(1−𝑅𝑒𝑠𝑖𝑠𝑡𝑎𝑛𝑐𝑒2)*...*(1−𝑅𝑒𝑠𝑖𝑠𝑡𝑎𝑛𝑐𝑒𝑁)]−[1−(1−𝑅𝑒𝑠𝑅𝑒𝑑𝑢𝑐𝑡.1)*(1−𝑅𝑒𝑠𝑅𝑒𝑑𝑢𝑐𝑡.2)*...*(1−𝑅𝑒𝑠𝑅𝑒𝑑𝑢𝑐𝑡.𝑁)]

For example, using Bullet Resists and Reductions:

- 70% Spirit Resist from Viscous' Goo Ball

- 20% Spirit Resist from Spirit Armor

- -12% Spirit Resist from Spirit Strike

- -12% Spirit Resist from Mystic Vulnerability

- -24% Spirit Resist from Crippling Headshot

[1−((1−0.7)*(1−0.2))]−[1−((1−0.12)*(1−0.12)*(1−0.24))]=35%SpiritResist

The final Resistance can go negative, and this multiplies the damage taken of that type. For example:

- 30% resist= 70% of the damage from the weapon or ability.

- 0% resist = 100% of the damage from the weapon or ability.

- -30% resist = 130% of the damage from the weapon or ability.

Items like Headshot Booster grant a flat added bullet damage, this bonus damage is not multiplied by weapon damage but is subject to resistance reduction/increase in damage.

## Effective Health

Include graph of effective health as a function of Damage Reduction. In the mean time, feel free to refer to this Desmos graph.

Include graph of effective damage increase from using 15%, 30%, and 45% Resistance Reduction as a function of the target's original Damage Reduction. In the mean time, feel free to refer to this Desmos graph.

## Sources of Damage Resistance

### Bullet Resist

| Name | Cost | Category | Stat change |

| --- | --- | --- | --- |

| 轻盈飞步 | 1,600 | Weapon | +6% Bullet Resist |

| 近战蓄力 | 1,600 | Weapon | +6% Bullet Resist |

| 狂战士 | 3,200 | Weapon | +8% Bullet Resist |

| 层层防御 | 3,200 | Weapon | +2% Bullet Resist |

| 英雄光环 | 3,200 | Weapon | +17% Bullet Resist |

| 粉碎重拳 | 6,400 | Weapon | +12% Bullet Resist |

| 战斗背心 | 1,600 | Vitality | +18% Bullet Resist |

| 回应射击 | 1,600 | Vitality | +10% Bullet Resist |

| 武器防护 | 1,600 | Vitality | +18% Bullet Resist |

| 子弹坚甲 | 3,200 | Vitality | +30% Bullet Resist |

| 铜皮铁骨 | 3,200 | Vitality | +12% Bullet Resist |

| 传送石 | 3,200 | Vitality | +30% Bullet Resist |

| 幸免于难 | 6,400 | Vitality | +15% Bullet Resist |

| 不屈之志 | 6,400 | Vitality | +10% Bullet Resist |

| 虹吸弹 | 6,400 | Vitality | +10% Bullet Resist |

| 疗愈爆发 | 6,400 | Vitality | +10% Bullet Resist |

| 粉碎护甲 | 1,600 | Spirit | +9% Bullet Resist |

| 元灵压制 | 1,600 | Spirit | +8% Bullet Resist |

| 余威久久 | 3,200 | Spirit | +8% Bullet Resist |

| 回音碎片 | 6,400 | Spirit | +5% Bullet Resist |

- 猎怪弹 increases Bullet Resist vs. NPCs by +25%%.

- 层层防御 increases Bullet Resist by 2%% per stack per shot when hitting enemy heroes, maxing at 30%% Bullet Resist.

### Bullet Resist Reduction

| Name | Cost | Category | Stat change |

| --- | --- | --- | --- |

| 追猎 | 1,600 | Weapon | -6% Bullet Resist Reduction |

| 头弹弱防 | 1,600 | Weapon | -13% Bullet Resist Reduction |

| 炼金之火 | 3,200 | Weapon | -7% Bullet Resist Reduction |

| 空尖弹 | 3,200 | Weapon | -9% Bullet Resist Reduction |

| 猎人光环 | 3,200 | Weapon | -10% Bullet Resist Reduction |

| 头弹破防 | 6,400 | Weapon | -16% Bullet Resist Reduction |

| 粉碎重拳 | 6,400 | Weapon | -4% Bullet Resist Reduction |

| 锈蚀枪管 | 800 | Spirit | -8% Bullet Resist Reduction |

| 粉碎护甲 | 1,600 | Spirit | -10% Bullet Resist Reduction |

| 缴械魔咒 | 3,200 | Spirit | -13% Bullet Resist Reduction |

### Melee Resist

| Name | Cost | Category | Stat change |

| --- | --- | --- | --- |

| 近身决斗 | 800 | Weapon | +20% Melee Resist |

| 近身猛击 | 3,200 | Weapon | +30% Melee Resist |

| 符文手套 | Legendary | Weapon | +50% Melee Resist |

| 对等还击 | 800 | Vitality | +18% Melee Resist |

| 破阵之势 | 6,400 | Vitality | +25% Melee Resist |

| 痛苦脉冲 | 3,200 | Spirit | +18% Melee Resist |

### Spirit Resist

| Name | Cost | Category | Stat change |

| --- | --- | --- | --- |

| 殷红贡礼 | 3,200 | Weapon | +8% Spirit Resist |

| 沉默子弹 | 6,400 | Weapon | +12% Spirit Resist |

| 附魔师纹章 | 1,600 | Vitality | +18% Spirit Resist |

| 疗愈护符 | 1,600 | Vitality | +10% Spirit Resist |

| 元灵防护 | 1,600 | Vitality | +18% Spirit Resist |

| 驱散魔法 | 3,200 | Vitality | +10% Spirit Resist |

| 怒意之潮 | 3,200 | Vitality | +40% Spirit Resist |

| 元灵护体 | 3,200 | Vitality | +30% Spirit Resist |

| 治疗律动 | 6,400 | Vitality | +10% Spirit Resist |

| 不屈之志 | 6,400 | Vitality | +10% Spirit Resist |

| 灵力灌注 | 6,400 | Vitality | +10% Spirit Resist |

| 破咒护符 | 6,400 | Vitality | +18% Spirit Resist |

| 巫师护甲 | 6,400 | Vitality | +22% Spirit Resist |

| 冰天雪地 | 1,600 | Spirit | +6% Spirit Resist |

| 秘术脆弱 | 1,600 | Spirit | +8% Spirit Resist |

| 强效扩张 | 3,200 | Spirit | +10% Spirit Resist |

| 极地冰暴 | 6,400 | Spirit | +10% Spirit Resist |

| 回音碎片 | 6,400 | Spirit | +5% Spirit Resist |

| 伤上加伤 | 6,400 | Spirit | +17% Spirit Resist |

| 身躯虚化 | 6,400 | Spirit | +30% Spirit Resist |

| 敌之灾患 | 6,400 | Spirit | +40% Spirit Resist |

### Spirit Resist Reduction

| Name | Cost | Category | Stat change |

| --- | --- | --- | --- |

| 碎灵子弹 | 1,600 | Weapon | -8% Spirit Resist Reduction |

| 元灵撕裂 | 3,200 | Weapon | -8% Spirit Resist Reduction |

| -7% Spirit Resist Reduction |  |  |  |

| 头弹破防 | 6,400 | Weapon | -16% Spirit Resist Reduction |

| 大伤元气 | 800 | Spirit | -6% Spirit Resist Reduction |

| 秘术脆弱 | 1,600 | Spirit | -8% Spirit Resist Reduction |

| 元灵衰竭 | 1,600 | Spirit | -9% Spirit Resist Reduction |

| 元灵收割 | 3,200 | Spirit | -12% Spirit Resist Reduction |

| 伤上加伤 | 6,400 | Spirit | -8% Spirit Resist Reduction |

| 聚焦透镜 | 6,400 | Spirit | -9% Spirit Resist Reduction |

- 元灵撕裂 reduces -7%% spirit resist on bullet hit from its component 碎灵子弹, as well as an additional -8%% spirit resist reduction per stack on headshots, up to a max of 4 stacks (-33% spirit resist total).
