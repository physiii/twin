for p in $(playerctl -l); do
    echo "Player: $p"
    echo "Status: $(playerctl -p "$p" status 2>/dev/null || echo 'N/A')"

    echo "Transport Info:"
    # Current position (seconds)
    current_position=$(playerctl -p "$p" position 2>/dev/null || echo '0')
    echo "  Current Position (sec): $current_position"

    # Maximum position / total duration (microseconds --> convert to seconds)
    total_us=$(playerctl -p "$p" metadata mpris:length 2>/dev/null || echo '0')
    if [ "$total_us" -gt 0 ]; then
        total_s=$(bc <<< "scale=2; $total_us / 1000000")
        echo "  Total Duration (sec): $total_s"
    else
        echo "  Total Duration (sec): N/A"
    fi

    # Playback volume
    echo "  Volume:       $(playerctl -p "$p" volume 2>/dev/null || echo 'N/A')"
    # Playback rate (speed)
    echo "  Playback Rate: $(playerctl -p "$p" rate 2>/dev/null || echo 'N/A')"
    echo "---------------------------------------------"
done
