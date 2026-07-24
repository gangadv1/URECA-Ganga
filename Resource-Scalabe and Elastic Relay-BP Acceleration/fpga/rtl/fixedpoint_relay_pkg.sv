// Bit-exact helpers shared by the new folded Relay-BP RTL path.
// Rounding is nearest, ties away from zero, matching reference/fixedpoint.py.
package fixedpoint_relay_pkg;
  function automatic longint signed round_shift_away(
      input longint signed value, input int unsigned shift);
    longint signed magnitude;
    begin
      if (shift == 0) begin
        round_shift_away = value;
      end else begin
        magnitude = value < 0 ? -value : value;
        magnitude = (magnitude + (64'sd1 <<< (shift - 1))) >>> shift;
        round_shift_away = value < 0 ? -magnitude : magnitude;
      end
    end
  endfunction

  function automatic longint signed saturate_signed(
      input longint signed value, input int unsigned width, input longint signed clip);
    longint signed min_value, max_value;
    begin
      min_value = -(64'sd1 <<< (width - 1));
      max_value = (64'sd1 <<< (width - 1)) - 1;
      if (clip >= 0 && -clip > min_value) min_value = -clip;
      if (clip >= 0 && clip < max_value) max_value = clip;
      if (value < min_value) saturate_signed = min_value;
      else if (value > max_value) saturate_signed = max_value;
      else saturate_signed = value;
    end
  endfunction

  function automatic longint signed memory_mix(
      input longint signed previous, input longint signed current,
      input int unsigned beta_int, input int unsigned m_shift,
      input int unsigned width, input longint signed clip);
    longint signed numerator;
    longint signed scale;
    begin
      scale = 64'sd1 <<< m_shift;
      numerator = beta_int * previous + (scale - beta_int) * current;
      memory_mix = saturate_signed(round_shift_away(numerator, m_shift), width, clip);
    end
  endfunction
endpackage
