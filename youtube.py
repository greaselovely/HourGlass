        # # Upload to YouTube
        # date_obj = datetime.now()
        # formatted_date = date_obj.strftime("%m/%d/%Y")
        # video_title = f"VLA {formatted_date}"
        # video_description = f"@NRAO Very Large Array Time Lapse for {formatted_date}"
        
        # video_id, youtube_client = upload_to_youtube(video_path, video_title, video_description)
        
        # if video_id and youtube_client:
        #     message_processor(f"Video uploaded to YouTube ID: {video_id}", ntfy=True)
            
        #     # Now, add the video to the playlist
        #     success, message = add_video_to_playlist(youtube_client, video_id, "VLA")
        #     if success:
        #         message_processor(message, ntfy=True)
        #     else:
        #         message_processor(message, ntfy=True)
        # else:
        #     message_processor("Failed to upload video to YouTube", "error", ntfy=True)
        #     message_processor(f"{os.path.basename(video_path)} saved", ntfy=True, print_me=False)