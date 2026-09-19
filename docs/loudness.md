# Loudness: what to do with the audio of a recording

A recording of an event is quiet, uneven and spiky. The two defences this package was built on
measured -36 LUFS integrated, some 20 LU below anything a laptop plays comfortably, with peaks 30 dB
above the speech. The four voices of one of them spanned 10.9 LU:

| Voice | Integrated | Peak |
|---|---|---|
| Second opponent, over a connection | -34.6 LUFS | -14.9 dBFS |
| Chair | -37.9 | -12.8 |
| Candidate | -41.1 | -7.9 |
| First opponent, at the back of the room | -45.5 | -8.4 |

Four to seven of those LU sit inside a single part, so a listener reaches for the volume control at
every handover.

## Speech

The chain, in order, and each step has a job the next cannot do:

1. A leveller, with its gain smoothed over about 6 s. That is slow enough to follow a speaker and
   too slow to follow a syllable, which is what makes it a leveller rather than a compressor.
2. A true-peak limiter. A recording of a room has a crest factor of 30 dB or more, and one chair
   scraping is enough to eat the headroom that the gain needs.
3. A measuring pass over the levelled, limited signal.
4. One linear gain to the target.

Steps 2 and 4 are the pair that matters. `loudnorm` asked for a target it cannot reach with a plain
gain, because that gain would put the peaks over the ceiling, falls back to a dynamic mode of its
own and does not say so: a run that names `linear=true` can be compressing throughout. Taking the
peaks first is what keeps the last step linear.

On a 90 s exchange between the quietest voice and the candidate, the source spread of 4.3 LU came to
2.3 LU under loudness normalisation alone, and to 1.4 LU with the leveller in front of it. Smoothing
windows of 2 s and 10 s both did worse than 6 s.

## Music

The opposite. Loudness range is content in music: a crescendo, a quiet entry, the step from a solo
to a tutti. Levelling flattens the piece into the thing the composer wrote around. So a musical part
is given the gain and a limiter set so that it should never engage, and nothing else, and its
loudness range is left alone. EBU Tech 3343 says as much for classical programmes: normalise to the
target and accept a wide range.

`treatment()` decides from the segment map, at a fifth of the part by duration. The threshold is
deliberately generous, because a demonstration inside a lecture is music by class and is not a
reason to stop levelling the voices around it.

## A concert with talk in it

Neither treatment is right for the whole file. Levelling the programme squashes the music; leaving
it alone leaves the host 10 LU under the band. The fix is not a filter but the segment map: set the
gain from the music and lift only the spoken segments. `cut_parts` does not do this yet, and a part
that is mostly music with introductions in it is the case to watch.

## Targets

-16 LUFS with a ceiling of -1.5 dBTP is the default here, the figure the web is mixed to; podcasts
sit at -16 and Spotify and YouTube around -14. Broadcast delivery under EBU R128 is -23 LUFS with
-1 dBTP, which `--target -23 --true-peak -1` gives. An archival master is a separate question: keep
it flat, and put the levelling in the derivative.
